"""Task036 T0b-M thin adapter for orientation-correct port transfer.

The adapter builds the primal map ``J`` from geometrically matched edge and
face-interior blocks and the already-built trace constraint maps.  It never
forms a dense global transfer matrix.  The defining identity is

    C_target J = Q C_source,

where ``Q`` is the unphased, orientation-aware original-trace transfer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import subprocess
import tempfile
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from scipy import sparse
from dolfinx import cpp, fem
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.run_task036_one_cell_discrete_bloch import (
    _authority_config,
    _mode_basis,
    _one_cell_config,
)
from benchmarks.task036_transfer_capacity import (
    complex_gaussian_holdout_multiplier,
    singular_tail_summary,
)
from src.coupling.hybrid_internal_modes import (
    _DistributedTwoDimensionalEvaluator,
    build_hybrid_internal_mode_coupling,
)
from src.constraints.floquet_3d_high_order import (
    _build_entity_dof_map,
    _face_vertex_permutation,
)
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.high_order_floquet_trace import (
    edge_coefficient_transform,
    face_coefficient_transform,
)
from src.geometry.tetra_mesh_audit import canonical_entity_key
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.common_3d_fields import _interpolated_mode_field
from src.solvers.dtn_port_3d import (
    _ReusableSurfaceComponentAssembler,
    _assembly_time_full_operator_residual,
    _assign_fe_solution_from_assembly_time_condensation,
    _assemble_unconstrained_vector,
    _auxiliary_direct_tangential_projection_audit,
    _gather_auxiliary_values,
    _port_power_metrics,
    _traction_vector,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    _external_diffraction_order_rows,
)
from src.solvers.hybrid_local_dtn import (
    assemble_hybrid_local_dtn_system,
    build_hybrid_local_full_matrix_solve_action,
    build_hybrid_local_incoming_load_columns,
    build_hybrid_local_one_sided_schur_action,
)
from src.solvers.hybrid_static_field_recovery import _add_external_tractions
from src.postprocessing.rta_3d import compute_volume_absorption_3d
from src.solvers.hybrid_port_metric import (
    EndpointTraceMassSelection,
    build_endpoint_trace_mass_actions,
)
from src.solvers.hybrid_strong_trace_direct import (
    build_hybrid_strong_trace_interface_map,
)
from src.solvers.hcurl_assembly_time_condensation import TraceConstraintMap
from src.solvers.one_cell_discrete_bloch import (
    ProjectedTwoPortSchur,
    compose_projected_two_port_schur,
    identify_endpoint_active_rows,
)
from src.solvers.one_cell_discrete_bloch import (
    _active_values_for_port,
    build_one_cell_two_port_schur_action,
    endpoint_cauchy_columns,
)
from src.solvers.hybrid_trace_chain import solve_block_tridiagonal_recursive
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)


SparseRow = tuple[np.ndarray, np.ndarray]

V9_MODE_POOL_SOURCE_SHA = "d3bed04a33778baf84d6c0938bd4ad305cb36edf"
V9_MODE_POOL_JSON_SHA = "f1bec4e1bf156eb05e2d337941e4b65f783c00d19e1c0cc9bb85fe23296daa7d"
V9_MODE_POOL_NPZ_SHA = "e61c314e9bfa66264245c65e9b6d91ed979577d6fd578fe4af6390e4599d5210"
V9_MODE_POOL_JSON = Path("benchmarks/artifacts/task036/direct_d1b/r1b1a_mode_pool/d3bed04a-20260803-v9-formal-span/runner_result.json")
V9_MODE_POOL_NPZ = V9_MODE_POOL_JSON.with_suffix(".npz")


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_v9_mode_pool(
    json_path: Path = V9_MODE_POOL_JSON,
    npz_path: Path = V9_MODE_POOL_NPZ,
    *,
    expected_json_sha: str = V9_MODE_POOL_JSON_SHA,
    expected_npz_sha: str = V9_MODE_POOL_NPZ_SHA,
) -> dict[str, Any]:
    """Read the fixed v9 pool and enforce its source/shape/block identity."""

    if _sha256(json_path) != expected_json_sha:
        raise ValueError("The bound v9 JSON hash does not match.")
    record = json.loads(json_path.read_text(encoding="utf-8"))
    if (record["status"], record["source"]["sha"]) != (
        "mode-pool-qualified",
        V9_MODE_POOL_SOURCE_SHA,
    ):
        raise ValueError("The bound v9 status/source identity does not match.")
    manifest = record["canonical_npz_manifest"]
    if _sha256(npz_path) != expected_npz_sha or manifest["sha256"] != expected_npz_sha:
        raise ValueError("The v9 mode-pool NPZ hash does not match its record.")
    with np.load(npz_path, allow_pickle=False) as archive:
        arrays = {name: np.asarray(archive[name]).copy() for name in archive.files}
    if (
        arrays["right_states"].shape != (3240, 184)
        or arrays["adjoint_states"].shape != (3240, 184)
        or arrays["right_multipliers"].shape != (184,)
        or arrays["adjoint_multipliers"].shape != (184,)
    ):
        raise ValueError("The v9 augmented state/multiplier shapes are not canonical.")
    if not np.array_equal(arrays["right_block_ids"], arrays["adjoint_block_ids"]):
        raise ValueError("The v9 right/adjoint block identities differ.")
    return {"record": record, **arrays}


def v9_endpoint_cauchy_arrays(
    action: Any,
    pool: Mapping[str, Any],
    endpoint_transfers: Mapping[str, tuple[SparsePortTransfer, SparsePortTransfer]] | None = None,
) -> dict[str, Any]:
    """Extract both endpoint Cauchy arrays without choosing orientation."""

    right_electric, right_traction, adjoint_electric, adjoint_traction = endpoint_cauchy_columns(
        action,
        pool["right_states"],
        pool["adjoint_states"],
        multipliers=pool["right_multipliers"],
        adjoint_multipliers=pool["adjoint_multipliers"],
    )
    left = action.left_rows
    right_joint = np.vstack((right_electric[left:], -right_traction[left:]))
    left_joint = np.vstack((right_electric[:left], right_traction[:left]))
    adjoint_right = np.vstack((adjoint_electric[left:], -adjoint_traction[left:]))
    adjoint_left = np.vstack((adjoint_electric[:left], adjoint_traction[:left]))
    errors = [
        np.linalg.norm(right_joint - left_joint * pool["right_multipliers"])
        / max(np.linalg.norm(right_joint), 1.0e-30),
        np.linalg.norm(adjoint_right - adjoint_left * pool["adjoint_multipliers"])
        / max(np.linalg.norm(adjoint_right), 1.0e-30),
    ]
    endpoint_identity = dict(zip(
        ("right_relative_error", "adjoint_relative_error"), map(float, errors)
    ))
    if max(endpoint_identity.values()) > 1.0e-8:
        raise AssertionError(
            f"v9 endpoint outward identity failed: {endpoint_identity}"
        )
    result = {
        "right_electric": right_electric,
        "right_traction": right_traction,
        "adjoint_electric": adjoint_electric,
        "adjoint_traction": adjoint_traction,
        "right_multipliers": np.asarray(
            pool["right_multipliers"], dtype=np.complex128
        ).copy(),
        "adjoint_multipliers": np.asarray(
            pool["adjoint_multipliers"], dtype=np.complex128
        ).copy(),
        "block_ids": pool["right_block_ids"].copy(),
        "endpoint_identity": endpoint_identity,
    }
    if endpoint_transfers is None:
        return result
    mapped: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    map_gate: dict[str, Any] = {}
    for side, (forward, reverse) in endpoint_transfers.items():
        mapped[side] = (
            forward.primal(right_electric[:left]),
            reverse.dual(right_traction[:left]),
            forward.primal(adjoint_electric[:left]),
            reverse.dual(adjoint_traction[:left]),
        )
        map_gate[side] = {
            "source_size": int(forward.source_size),
            "target_size": int(forward.target_size),
            "roundtrip": "passed",
            "dual_pairing": "passed",
            "traction_action": "reverse.dual",
        }
    bottom = mapped["bottom"]
    top = mapped["top"]
    result.update(
        {
            "right_electric": np.vstack((top[0], bottom[0])),
            "right_traction": np.vstack((top[1], bottom[1])),
            "adjoint_electric": np.vstack((top[2], bottom[2])),
            "adjoint_traction": np.vstack((top[3], bottom[3])),
            "map_gate": map_gate,
            "endpoint_transfers": endpoint_transfers,
        }
    )
    return result


def _v9_core_complement_data(
    columns: np.ndarray,
    white_core: np.ndarray,
    gc_action: Any,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    """Measure the G_C-complement rank without selecting or splitting blocks."""

    values, core = (
        np.asarray(item, dtype=np.complex128) for item in (columns, white_core)
    )
    if values.ndim != 2 or values.shape[0] != 2400:
        raise ValueError("v9 Cauchy columns must have shape (2400, n).")
    metric_values = gc_action(values)
    complement = values - core @ (core.conj().T @ metric_values)
    metric_complement = gc_action(complement)
    gram_raw = complement.conj().T @ metric_complement
    gram = 0.5 * (gram_raw + gram_raw.conj().T)
    spectrum = np.linalg.eigvalsh(gram)
    scale = max(float(spectrum[-1]), 1.0e-30)
    rank = int(np.count_nonzero(spectrum > 1.0e-20 * scale))
    return {
        "raw_columns": int(values.shape[1]),
        "complement_rank_rcond_1e_10": rank,
        "core_orthogonality_relative": float(
            np.linalg.norm(core.conj().T @ metric_complement)
            / max(np.linalg.norm(core.conj().T @ metric_values), 1.0e-30)
        ),
    }, complement, metric_complement


def v9_core_complement_rank(
    columns: np.ndarray,
    white_core: np.ndarray,
    gc_action: Any,
) -> dict[str, Any]:
    """Measure the G_C-complement rank without selecting or splitting blocks."""

    return _v9_core_complement_data(columns, white_core, gc_action)[0]


def select_v9_block_prefixes(
    right_columns: Mapping[str, np.ndarray],
    adjoint_columns: Mapping[str, np.ndarray],
    block_ids: np.ndarray,
    right_metric_columns: Mapping[str, np.ndarray],
    adjoint_metric_columns: Mapping[str, np.ndarray],
    requested: tuple[int, ...] = (40, 80, 120),
) -> dict[str, Any]:
    """Select whole blocks using only the four projected metric Grams."""
    block_ids = np.asarray(block_ids, dtype=np.int64)
    sides = tuple(right_columns)
    if (
        sides != tuple(adjoint_columns)
        or sides != tuple(right_metric_columns)
        or sides != tuple(adjoint_metric_columns)
    ):
        raise ValueError("right, adjoint, and metric side keys must agree")
    groups = {
        int(block): np.flatnonzero(block_ids == block)
        for block in np.unique(block_ids)
    }

    def gram_data(
        matrix: np.ndarray, reference_scale: float
    ) -> tuple[int, np.ndarray, np.ndarray, np.ndarray]:
        hermitian = 0.5 * (matrix + matrix.conj().T)
        eigenvalues, vectors = np.linalg.eigh(hermitian)
        keep = eigenvalues > 1.0e-20 * reference_scale
        inverse = (vectors[:, keep] / eigenvalues[keep]) @ vectors[:, keep].conj().T
        whitening = vectors[:, keep] / np.sqrt(eigenvalues[keep])
        return int(np.count_nonzero(keep)), inverse, whitening, eigenvalues

    def schur(
        gram: np.ndarray,
        candidate: np.ndarray,
        selected: np.ndarray,
        selected_inverse: np.ndarray | None,
    ) -> np.ndarray:
        result = gram[np.ix_(candidate, candidate)]
        if selected.size:
            cross = gram[np.ix_(candidate, selected)]
            result -= cross @ selected_inverse @ cross.conj().T
        return 0.5 * (result + result.conj().T)

    cached: dict[str, dict[str, Any]] = {}
    for side in sides:
        right = np.asarray(right_columns[side], dtype=np.complex128)
        adjoint = np.asarray(adjoint_columns[side], dtype=np.complex128)
        right_metric = np.asarray(right_metric_columns[side], dtype=np.complex128)
        adjoint_metric = np.asarray(adjoint_metric_columns[side], dtype=np.complex128)
        if (
            right.shape != adjoint.shape
            or right.shape != right_metric.shape
            or right.shape != adjoint_metric.shape
            or right.shape[1] != len(block_ids)
        ):
            raise ValueError("right, adjoint, metric, and block columns are inconsistent")
        gram = {
            "right": 0.5 * (right.conj().T @ right_metric + right_metric.conj().T @ right),
            "adjoint": 0.5 * (adjoint.conj().T @ adjoint_metric + adjoint_metric.conj().T @ adjoint),
        }
        cached[side] = {
            "gram": gram,
            "scale": {
                family: max(float(np.linalg.eigvalsh(matrix)[-1].real), 1.0e-30)
                for family, matrix in gram.items()
            },
            "pairing": adjoint.conj().T @ right_metric,
        }
    right_ranks = {side: 0 for side in sides}
    remaining, order, increments = set(groups), [], {}
    selected_indices = np.empty(0, dtype=np.int64)
    full_traces = {
        side: {family: max(float(np.trace(cached[side]["gram"][family]).real), 1.0e-30)
               for family in ("right", "adjoint")}
        for side in sides
    }
    while remaining and max(right_ranks.values()) < max(requested):
        selected_inverses = {
            side: {
                family: (
                    gram_data(
                        cached[side]["gram"][family][np.ix_(selected_indices, selected_indices)],
                        cached[side]["scale"][family],
                    )[1]
                    if selected_indices.size
                    else None
                )
                for family in ("right", "adjoint")
            }
            for side in sides
        }
        candidates = []
        for block in sorted(remaining):
            candidate = groups[block]
            block_inc: dict[str, dict[str, int]] = {}
            gain = 0.0
            for side in sides:
                block_inc[side] = {}
                for family in ("right", "adjoint"):
                    residual = schur(
                        cached[side]["gram"][family],
                        candidate,
                        selected_indices,
                        selected_inverses[side][family],
                    )
                    rank, _, _, _ = gram_data(
                        residual, cached[side]["scale"][family]
                    )
                    block_inc[side][family] = rank
                    gain += float(np.trace(residual).real) / full_traces[side][family]
            if max(
                right_ranks[side] + block_inc[side]["right"] for side in sides
            ) <= max(requested):
                candidates.append((gain, block, block_inc))
        if not candidates:
            break
        gain, block, block_inc = max(candidates, key=lambda item: (item[0], -item[1]))
        order.append(block)
        increments[block] = block_inc
        remaining.remove(block)
        selected_indices = np.concatenate((selected_indices, groups[block]))
        for side in sides:
            right_ranks[side] += block_inc[side]["right"]

    def stats(side: str, family: str, indices: np.ndarray) -> tuple[dict[str, Any], np.ndarray]:
        gram = cached[side]["gram"][family]
        full_scale = cached[side]["scale"][family]
        rank, inverse, whitening, _ = gram_data(
            gram[np.ix_(indices, indices)], full_scale
        )
        residual = gram - gram[:, indices] @ inverse @ gram[indices, :] if indices.size else gram
        residual = 0.5 * (residual + residual.conj().T)
        residual_data = gram_data(residual, full_scale)
        diagonal = np.maximum(np.real(np.diag(residual)), 0.0)
        denominator = np.maximum(np.real(np.diag(gram)), 1.0e-30)
        report = {
            "selected_rank": rank,
            "captured_energy": float(1.0 - np.trace(residual).real / full_traces[side][family]),
            "worst_projection_residual": float(np.sqrt(np.max(diagonal / denominator))),
            "complement_rank": residual_data[0],
            "complement_tail": float(max(residual_data[3][-1].real, 0.0) / full_scale),
        }
        return report, whitening

    prefixes: dict[str, Any] = {}
    for target in requested:
        selected_blocks, selected_right = [], {side: 0 for side in sides}
        for block in order:
            next_r = {
                side: selected_right[side] + increments[block][side]["right"]
                for side in sides
            }
            if max(next_r.values()) > target:
                break
            selected_blocks.append(block)
            selected_right = next_r
        indices = (
            np.concatenate([groups[block] for block in selected_blocks])
            if selected_blocks
            else np.empty(0, dtype=np.int64)
        )
        per_side, pairing = {}, {}
        for side in sides:
            right_report, right_basis = stats(side, "right", indices)
            adjoint_report, adjoint_basis = stats(side, "adjoint", indices)
            per_side[side] = {"right": right_report, "adjoint": adjoint_report}
            if not indices.size:
                pairing[side] = {
                    "right_trial_rank": 0,
                    "adjoint_test_rank": 0,
                    "rank": 0,
                    "condition": None,
                }
                continue
            pairing_matrix = adjoint_basis.conj().T @ cached[side]["pairing"][np.ix_(indices, indices)] @ right_basis
            singular = np.linalg.svd(pairing_matrix, compute_uv=False)
            scale = max(float(singular[0]), 1.0e-30)
            pairing[side] = {
                "right_trial_rank": int(right_basis.shape[1]),
                "adjoint_test_rank": int(adjoint_basis.shape[1]),
                "rank": int(np.count_nonzero(singular > 1.0e-10 * scale)),
                "condition": float(singular[0] / singular[-1]) if singular[-1] > 1.0e-30 else None,
            }
        selected_right = {side: per_side[side]["right"]["selected_rank"] for side in sides}
        prefixes[str(target)] = {
            "requested_r": int(target),
            "effective_r": int(max(selected_right.values())),
            "selected_right_rank_by_side": {side: int(selected_right[side]) for side in sides},
            "selected_adjoint_rank_by_side": {
                side: int(per_side[side]["adjoint"]["selected_rank"]) for side in sides
            },
            "raw_column_count": int(indices.size),
            "selected_block_count": len(selected_blocks),
            "selected_block_ids_sha256": hashlib.sha256(np.asarray(selected_blocks, dtype=np.int64).tobytes()).hexdigest(),
            "selected_indices_sha256": hashlib.sha256(indices.astype(np.int64).tobytes()).hexdigest(),
            "per_side": per_side,
            "pairing_by_side": pairing,
        }
    return {"prefixes": prefixes, "ordering": order}


def build_global_two_end_petrov_fixture(
    *,
    bottom_core: np.ndarray,
    top_core: np.ndarray,
    right_bottom_scale: np.ndarray,
    right_top_scale: np.ndarray,
    adjoint_bottom_core: np.ndarray,
    adjoint_top_core: np.ndarray,
    adjoint_bottom_scale: np.ndarray,
    adjoint_top_scale: np.ndarray,
    bottom_corrector: np.ndarray,
    top_corrector: np.ndarray,
    adjoint_bottom_corrector: np.ndarray,
    adjoint_top_corrector: np.ndarray,
    block_ids: np.ndarray,
    selected_indices: np.ndarray,
    top_block_ids: np.ndarray,
    requested_r: int,
    left_port: ProjectedTwoPortSchur,
    right_port: ProjectedTwoPortSchur,
    rhs: np.ndarray,
) -> dict[str, Any]:
    """Solve a tiny two-end Petrov system from shared primal/test columns."""
    if requested_r not in (0, 40, 80, 120):
        raise ValueError("B1 corrector checkpoints must be 0, 40, 80, or 120.")
    block_ids = np.asarray(block_ids, dtype=np.int64)
    top_block_ids = np.asarray(top_block_ids, dtype=np.int64)
    selected = np.asarray(selected_indices, dtype=np.int64)
    if not np.array_equal(block_ids, top_block_ids):
        raise ValueError("Bottom and top corrector block identities are misaligned.")
    if np.any((selected < 0) | (selected >= len(block_ids))):
        raise ValueError("Selected corrector indices are outside the shared pool.")
    for block in np.unique(block_ids[selected]):
        if not np.all(np.isin(np.flatnonzero(block_ids == block), selected)):
            raise ValueError("A selected corrector block was split.")

    maps: list[np.ndarray] = []
    for core_bottom, core_top, bottom_scale, top_scale, corr_bottom, corr_top in (
        (
            bottom_core,
            top_core,
            right_bottom_scale,
            right_top_scale,
            bottom_corrector,
            top_corrector,
        ),
        (
            adjoint_bottom_core,
            adjoint_top_core,
            adjoint_bottom_scale,
            adjoint_top_scale,
            adjoint_bottom_corrector,
            adjoint_top_corrector,
        ),
    ):
        core_bottom = np.asarray(core_bottom, dtype=np.complex128)
        core_top = np.asarray(core_top, dtype=np.complex128)
        bottom_scale = np.asarray(bottom_scale, dtype=np.complex128)
        top_scale = np.asarray(top_scale, dtype=np.complex128)
        if core_bottom.shape != core_top.shape or (
            bottom_scale.shape != top_scale.shape
            or core_bottom.shape[1] != bottom_scale.size
        ):
            raise ValueError("Two-end core maps and propagation scales differ.")
        core = np.vstack(
            (
                core_bottom * bottom_scale[None, :],
                core_top * top_scale[None, :],
            )
        )
        correction = np.vstack(
            (
                np.asarray(corr_bottom, dtype=np.complex128)[:, selected],
                np.asarray(corr_top, dtype=np.complex128)[:, selected],
            )
        )
        maps.append(np.hstack((core, correction)))
    right_map, adjoint_map = maps
    composed, _ = compose_projected_two_port_schur(left_port, right_port)
    operator = np.block(
        [[composed.S_LL, composed.S_LR], [composed.S_RL, composed.S_RR]]
    )
    rhs = np.asarray(rhs, dtype=np.complex128)
    ranges: list[np.ndarray] = []
    raw_ranks: list[int] = []
    for values in (right_map, adjoint_map):
        left, singular, _ = np.linalg.svd(values, full_matrices=False)
        rank = int(np.count_nonzero(singular > 1.0e-10 * singular[0]))
        ranges.append(left[:, :rank])
        raw_ranks.append(rank)
    right_range, adjoint_range = ranges
    right_rank, adjoint_rank = raw_ranks
    left_factor, paired_singular, right_factor_h = np.linalg.svd(
        adjoint_range.conj().T @ right_range, full_matrices=False
    )
    paired_rank = int(np.count_nonzero(paired_singular > 1.0e-10 * paired_singular[0]))
    if paired_rank == 0:
        raise ValueError("Global primal/test maps have no paired range.")
    scale = 1.0 / np.sqrt(paired_singular[:paired_rank])
    right_white = right_range @ right_factor_h.conj().T[:, :paired_rank] * scale
    adjoint_white = adjoint_range @ left_factor[:, :paired_rank] * scale
    reduced = adjoint_white.conj().T @ operator @ right_white
    reduced_rhs = adjoint_white.conj().T @ rhs
    coefficients = np.linalg.solve(reduced, reduced_rhs)
    lifted = right_white @ coefficients
    direct = np.linalg.solve(operator, rhs)
    return {
        "global_primal_shape": list(right_map.shape),
        "raw_trial_rank": right_rank,
        "raw_test_rank": adjoint_rank,
        "paired_effective_rank": paired_rank,
        "selected_raw_corrector_columns": int(selected.size),
        "selected_whole_block_count": int(np.unique(block_ids[selected]).size),
        "pairing_condition": float(
            paired_singular[0] / paired_singular[paired_rank - 1]
        ),
        "requested_r": int(requested_r),
        "reduced_dimension": int(reduced.shape[0]),
        "petrov_stationarity_relative": float(
            np.linalg.norm(adjoint_white.conj().T @ (operator @ lifted - rhs))
            / max(np.linalg.norm(adjoint_white.conj().T @ rhs), 1.0e-30)
        ),
        "direct_solution_relative": float(
            np.linalg.norm(lifted - direct) / max(np.linalg.norm(direct), 1.0e-30)
        ),
    }


def build_b1_harmonic_extension(
    compact_blocks: Mapping[str, np.ndarray], endpoint_electric: np.ndarray
) -> tuple[np.ndarray, np.ndarray, dict[str, int]]:
    """Extend shared two-end electric columns through the nine interior planes."""

    bottom_diagonal = np.asarray(compact_blocks["bottom_diagonal"])
    middle = np.asarray(compact_blocks["middle_diagonal"])
    top_diagonal = np.asarray(compact_blocks["top_diagonal"])
    lower = np.asarray(compact_blocks["lower"])
    upper = np.asarray(compact_blocks["upper"])
    endpoint = np.asarray(endpoint_electric, dtype=np.complex128)
    plane_size = bottom_diagonal.shape[0]
    if endpoint.shape[0] != 2 * plane_size:
        raise ValueError("Two-end electric columns have the wrong row count.")
    bottom = endpoint[:plane_size]
    top = endpoint[plane_size:]
    zero = np.zeros_like(bottom)
    interior, record = solve_block_tridiagonal_recursive(
        [middle] * 9,
        [lower] * 8,
        [upper] * 8,
        [-lower @ bottom] + [zero.copy() for _ in range(7)] + [-upper @ top],
    )
    trace = np.vstack((bottom, interior, top))
    endpoint_residual = np.vstack(
        (
            bottom_diagonal @ bottom + upper @ interior[:plane_size],
            lower @ interior[-plane_size:] + top_diagonal @ top,
        )
    )
    return trace, endpoint_residual, record


def build_primal_reachable_pod_prefixes(
    teacher_by_side: Mapping[str, np.ndarray],
    teacher_metric_by_side: Mapping[str, np.ndarray],
    global_core_by_side: Mapping[str, np.ndarray],
    global_core_metric_by_side: Mapping[str, np.ndarray],
    source_keys_by_side: Mapping[str, tuple[tuple[Any, ...], ...]],
    requested: tuple[int, ...] = (0, 40, 80, 96, 120),
) -> dict[str, Any]:
    """Build shared two-end primal POD correction prefixes."""

    sides = ("bottom", "top")
    if tuple(teacher_by_side) != sides:
        raise ValueError("Teacher sides must be bottom and top.")
    if any(
        tuple(source_keys_by_side[side]) != tuple(source_keys_by_side["bottom"])
        for side in sides[1:]
    ):
        raise ValueError("Bottom and top source-column identities differ.")
    teacher = {side: np.asarray(teacher_by_side[side], dtype=np.complex128) for side in sides}
    teacher_metric = {
        side: np.asarray(teacher_metric_by_side[side], dtype=np.complex128)
        for side in sides
    }
    core = {side: np.asarray(global_core_by_side[side], dtype=np.complex128) for side in sides}
    core_metric = {
        side: np.asarray(global_core_metric_by_side[side], dtype=np.complex128)
        for side in sides
    }
    columns = teacher["bottom"].shape[1]
    rows = teacher["bottom"].shape[0]
    core_columns = core["bottom"].shape[1]
    if rows <= 0 or core_columns <= 0 or columns != len(source_keys_by_side["bottom"]):
        raise ValueError("Reachable teacher/core column identity is not fixed.")
    if any(
        teacher[side].shape != (rows, columns)
        or teacher_metric[side].shape != (rows, columns)
        or core[side].shape != (rows, core_columns)
        or core_metric[side].shape != (rows, core_columns)
        for side in sides
    ):
        raise ValueError("Reachable teacher/core arrays have incompatible shapes.")
    teacher_singular = np.linalg.svd(
        np.vstack((teacher["bottom"], teacher["top"])),
        compute_uv=False,
    )
    teacher_scale = teacher_singular[0] if teacher_singular.size else 0.0
    raw_source_rank = int(
        np.count_nonzero(teacher_singular > 1.0e-10 * teacher_scale)
    )
    global_gram = sum(
        core[side].conj().T @ core_metric[side] for side in sides
    )
    global_gram = 0.5 * (global_gram + global_gram.conj().T)
    cross = sum(
        core[side].conj().T @ teacher_metric[side] for side in sides
    )
    coefficients = np.linalg.solve(global_gram, cross)
    residual = {
        side: teacher[side] - core[side] @ coefficients for side in sides
    }
    residual_metric = {
        side: teacher_metric[side] - core_metric[side] @ coefficients
        for side in sides
    }
    core_orthogonality = sum(
        core[side].conj().T @ residual_metric[side] for side in sides
    )
    core_orthogonality_relative = float(
        np.linalg.norm(core_orthogonality)
        / max(np.linalg.norm(cross), 1.0e-30)
    )
    residual_gram = sum(
        residual[side].conj().T @ residual_metric[side] for side in sides
    )
    residual_gram = 0.5 * (residual_gram + residual_gram.conj().T)
    eigenvalues, vectors = np.linalg.eigh(residual_gram)
    ordering = np.argsort(eigenvalues)[::-1]
    eigenvalues = np.real(eigenvalues[ordering])
    vectors = vectors[:, ordering]
    scale = max(float(eigenvalues[0]), 1.0e-30)
    keep = eigenvalues > (1.0e-10**2) * scale
    effective_source_rank = int(np.count_nonzero(keep))
    singular_values = np.sqrt(np.maximum(eigenvalues, 0.0))
    corrector_coefficients = vectors[:, :effective_source_rank]
    corrector_scale = np.sqrt(eigenvalues[:effective_source_rank])
    corrector_by_side = {
        side: residual[side] @ corrector_coefficients / corrector_scale
        for side in sides
    }
    corrector_metric = {
        side: residual_metric[side] @ corrector_coefficients / corrector_scale
        for side in sides
    }
    corrector_identity = sum(
        corrector_by_side[side].conj().T @ corrector_metric[side]
        for side in sides
    )
    prefixes: dict[str, Any] = {}
    total_energy = max(float(np.sum(eigenvalues)), 1.0e-30)
    for target in requested:
        effective = min(int(target), effective_source_rank)
        next_relative = (
            float(singular_values[effective] / singular_values[0])
            if effective < len(singular_values) and singular_values[0] > 0.0
            else 0.0
        )
        prefixes[str(target)] = {
            "requested_r": int(target),
            "effective_r": effective,
            "raw_checkpoint_dimension": core_columns + effective,
            "next_singular_relative": next_relative,
            "discarded_energy_relative": float(
                np.sum(eigenvalues[effective:]) / total_energy
            ),
        }
    return {
        "status": "trial_capacity_scaffold",
        "raw_source_columns": columns,
        "raw_source_rank": raw_source_rank,
        "effective_source_rank": effective_source_rank,
        "source_snapshot_singular_values": singular_values.tolist(),
        "global_core_orthogonality_relative": core_orthogonality_relative,
        "joint_corrector_metric_identity_relative": float(
            np.linalg.norm(corrector_identity - np.eye(effective_source_rank))
        ),
        "prefixes": prefixes,
        "corrector_by_side": corrector_by_side,
    }


def solve_b1_reduced_petrov(
    trace_basis: np.ndarray,
    endpoint_basis: np.ndarray,
    endpoint_action_basis: np.ndarray,
    test_basis: np.ndarray,
    endpoint_rhs: np.ndarray,
    full_rhs: np.ndarray,
    trace_action: Any,
) -> dict[str, Any]:
    """Solve one shared-column reduced Petrov system and audit its lift."""

    trace = np.asarray(trace_basis, dtype=np.complex128)
    endpoint = np.asarray(endpoint_basis, dtype=np.complex128)
    endpoint_action = np.asarray(endpoint_action_basis, dtype=np.complex128)
    test = np.asarray(test_basis, dtype=np.complex128)
    rhs_endpoint = np.asarray(endpoint_rhs, dtype=np.complex128)
    rhs_full = np.asarray(full_rhs, dtype=np.complex128)
    if (
        trace.shape[1] != endpoint.shape[1]
        or endpoint_action.shape != endpoint.shape
        or test.shape != endpoint.shape
    ):
        raise ValueError("Primal, test, and harmonic columns are misaligned.")
    right_u, right_s, right_vh = np.linalg.svd(endpoint, full_matrices=False)
    left_u, left_s, _ = np.linalg.svd(test, full_matrices=False)
    right_rank = int(np.count_nonzero(right_s > 1.0e-10 * right_s[0]))
    left_rank = int(np.count_nonzero(left_s > 1.0e-10 * left_s[0]))
    right_coeff = right_vh.conj().T[:, :right_rank] / right_s[:right_rank]
    left_range = left_u[:, :left_rank]
    right_range = right_u[:, :right_rank]
    action_range = endpoint_action @ right_coeff
    trace_range = trace @ right_coeff
    overlap_singular = np.linalg.svd(
        left_range.conj().T @ right_range, compute_uv=False
    )
    overlap_scale = overlap_singular[0] if overlap_singular.size else 0.0
    overlap_rank = int(
        np.count_nonzero(overlap_singular > 1.0e-10 * overlap_scale)
    )
    overlap_condition = (
        float(overlap_singular[0] / overlap_singular[overlap_rank - 1])
        if overlap_rank
        else None
    )
    best_coefficients, *_ = np.linalg.lstsq(
        action_range, rhs_endpoint, rcond=1.0e-10
    )
    best_trial_residual = float(
        np.linalg.norm(action_range @ best_coefficients - rhs_endpoint)
        / max(np.linalg.norm(rhs_endpoint), 1.0e-30)
    )
    reduced = left_range.conj().T @ action_range
    operator_singular = np.linalg.svd(reduced, compute_uv=False)
    operator_scale = operator_singular[0] if operator_singular.size else 0.0
    operator_rank = int(
        np.count_nonzero(operator_singular > 1.0e-10 * operator_scale)
    )
    if right_rank == 0 or left_rank == 0 or right_rank != left_rank:
        raise ValueError("B1 trial/test range ranks are not equal and nonzero.")
    operator_min_relative = float(
        operator_singular[-1] / max(operator_singular[0], np.finfo(float).tiny)
    )
    operator_condition = None if operator_singular[-1] == 0.0 else float(
        operator_singular[0] / operator_singular[-1]
    )
    diagnostics = {
        "trial_rank": right_rank,
        "test_rank": left_rank,
        "coordinate_overlap_rank_diagnostic": overlap_rank,
        "coordinate_overlap_condition_diagnostic": overlap_condition,
        "petrov_operator_rank": operator_rank,
        "petrov_operator_condition": operator_condition,
        "petrov_operator_min_relative_singular_value": operator_min_relative,
        "best_trial_endpoint_residual_relative": best_trial_residual,
        "reduced_dimension": int(reduced.shape[0]),
        "solve_status": "petrov_operator_rank_deficient",
        "petrov_stationarity_relative": None,
        "endpoint_residual_relative": None,
        "full_trace_residual_relative": None,
        "lifted_trace": None,
    }
    if operator_rank != right_rank:
        return diagnostics
    reduced_rhs = left_range.conj().T @ rhs_endpoint
    coefficients = np.linalg.solve(reduced, reduced_rhs)
    lifted = trace_range @ coefficients
    full_residual = np.asarray(trace_action(lifted) - rhs_full)
    stationarity = left_range.conj().T @ (action_range @ coefficients - rhs_endpoint)
    diagnostics.update(
        solve_status="solved",
        petrov_stationarity_relative=float(
            np.linalg.norm(stationarity) / max(np.linalg.norm(reduced_rhs), 1.0e-30)
        ),
        endpoint_residual_relative=float(
            np.linalg.norm(action_range @ coefficients - rhs_endpoint)
            / max(np.linalg.norm(rhs_endpoint), 1.0e-30)
        ),
        full_trace_residual_relative=float(
            np.linalg.norm(full_residual) / max(np.linalg.norm(rhs_full), 1.0e-30)
        ),
        lifted_trace=lifted,
    )
    return diagnostics


def _petsc_rows(matrix: PETSc.Mat, rows: np.ndarray) -> np.ndarray:
    """Gather a small fixed column block at explicitly ordered serial rows."""

    row_ids = np.asarray(rows, dtype=PETSc.IntType)
    columns = np.arange(matrix.getSize()[1], dtype=PETSc.IntType)
    return np.asarray(matrix.getValues(row_ids, columns), dtype=np.complex128)


def _joint_cauchy_metric_action(
    mass: Any, values: np.ndarray, *, alpha: float, k0: float
) -> np.ndarray:
    electric, traction = np.split(np.asarray(values), 2, axis=0)
    return np.vstack(
        (
            alpha * mass.multiply_columns(electric),
            alpha / k0**2 * mass.solve_columns(traction),
        )
    )


def _relative_matrix_error(left: np.ndarray, right: np.ndarray) -> float:
    return float(
        np.linalg.norm(left - right)
        / max(np.linalg.norm(left), np.linalg.norm(right), 1.0e-30)
    )


def _portable_cell_key(
    midpoint: np.ndarray, x_values: np.ndarray, y_values: np.ndarray
) -> tuple[int, int]:
    """Return a partition-independent structured-cell identity."""

    x_index = int(
        np.searchsorted(x_values, float(midpoint[0]), side="right") - 1
    )
    y_index = int(
        np.searchsorted(y_values, float(midpoint[1]), side="right") - 1
    )
    return (
        min(max(x_index, 0), len(x_values) - 2),
        min(max(y_index, 0), len(y_values) - 2),
    )


def _write_portable_frozen_trace_archive(
    raw_path: Path,
    output_path: Path,
    spaces: Any,
    cross_section: Any,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Convert MPI-partitioned traces to physical cell/interpolation keys."""

    if comm.size != 8:
        raise RuntimeError("Portable frozen-trace conversion requires MPI8.")
    with np.load(raw_path) as archive:
        raw = np.asarray(
            archive["Et_canonical_owned_dofs"], dtype=np.complex128
        )
        z_nm = np.asarray(archive["z_nm"], dtype=np.float64)
    expected_z_nm = np.arange(10.0, 111.0, 10.0)
    if z_nm.shape != (11,) or not np.allclose(
        z_nm, expected_z_nm, rtol=0.0, atol=1.0e-13
    ):
        raise RuntimeError(
            "Portable frozen trace z-plane identity mismatch: "
            f"measured={z_nm.tolist()}, expected={expected_z_nm.tolist()}."
        )
    transverse = spaces.transverse
    index_map = transverse.dofmap.index_map
    ownership_ranges = comm.allgather(tuple(map(int, index_map.local_range)))
    expected_ranges = [0, 165, 310, 460, 630, 780, 940, 1095, 1250]
    if ownership_ranges != list(zip(expected_ranges[:-1], expected_ranges[1:])):
        raise RuntimeError(
            "Portable frozen trace MPI8 ownership ranges mismatch: "
            f"measured={ownership_ranges}, expected={expected_ranges}."
        )
    if raw.shape != (len(z_nm), int(index_map.size_global)):
        raise ValueError("Frozen raw trace shape does not match transverse space.")
    first, last = map(int, index_map.local_range)
    owned = int(index_map.size_local)
    fields = [fem.Function(transverse) for _ in range(len(z_nm))]
    try:
        for field, values in zip(fields, raw, strict=True):
            field.x.array[:owned] = values[first:last]
            field.x.scatter_forward()
        mesh = transverse.mesh
        cell_count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
        geometry_dofmap = np.asarray(mesh.geometry.dofmap)
        cell_records = []
        for cell in range(cell_count):
            coordinates = np.asarray(mesh.geometry.x[geometry_dofmap[cell], :2])
            midpoint = np.mean(coordinates, axis=0)
            key = _portable_cell_key(
                midpoint,
                np.asarray(cross_section.x_values),
                np.asarray(cross_section.y_values),
            )
            points = cpp.fem.interpolation_coords(
                transverse.element._cpp_object,
                mesh.geometry._cpp_object,
                np.asarray([cell], dtype=np.int32),
            ).T
            cell_points = np.asarray(points[:, :2], dtype=np.float64)
            x0, x1 = np.min(coordinates[:, 0]), np.max(coordinates[:, 0])
            y0, y1 = np.min(coordinates[:, 1]), np.max(coordinates[:, 1])
            reference = np.column_stack(
                (
                    (cell_points[:, 0] - x0) / (x1 - x0),
                    (cell_points[:, 1] - y0) / (y1 - y0),
                )
            )
            cell_records.append((key, cell, cell_points, reference))
        local_points = np.vstack(
            [
                np.column_stack((cell_points, np.zeros(len(cell_points))))
                for _, _, cell_points, _ in cell_records
            ]
        )
        local_cell_keys = np.vstack(
            [
                np.repeat(np.asarray(key, dtype=np.int64)[None, :], len(cell_points), axis=0)
                for key, _, cell_points, _ in cell_records
            ]
        )
        evaluator = _DistributedTwoDimensionalEvaluator(
            fields[0], padding=1.0e-12
        )
        samples_by_plane = []
        for field in fields:
            evaluator.set_source(field)
            evaluated = evaluator.evaluate_points(
                local_points, cell_keys=local_cell_keys
            ).T[:, :2]
            offsets = np.cumsum([0, *[len(item[2]) for item in cell_records]])
            samples_by_plane.append(
                [
                    np.asarray(evaluated[offsets[i] : offsets[i + 1]], dtype=np.complex128)
                    for i in range(len(cell_records))
                ]
            )
        local_payload = [
            (
                key,
                cell,
                cell_points,
                reference,
                np.stack(
                    [samples_by_plane[plane][cell_index] for plane in range(len(fields))]
                ),
            )
            for cell_index, (key, cell, cell_points, reference) in enumerate(cell_records)
        ]
        gathered = comm.gather(local_payload, root=0)
        local_roundtrip_error = 0.0
        for plane_index, field in enumerate(fields):
            reconstructed = fem.Function(transverse)
            for _, cell, cell_points, _, samples in local_payload:

                def callback(
                    coordinates: np.ndarray,
                    expected_points=cell_points,
                    expected_values=samples[plane_index],
                ) -> np.ndarray:
                    raw_coordinates = np.asarray(coordinates, dtype=np.float64)
                    point_matrix = (
                        raw_coordinates.T
                        if raw_coordinates.shape[0] <= 3
                        else raw_coordinates
                    )
                    if point_matrix.shape[0] != expected_points.shape[0]:
                        raise RuntimeError("Portable cell interpolation point count changed.")
                    if not np.allclose(
                        point_matrix[:, :2], expected_points, rtol=0.0, atol=1.0e-13
                    ):
                        raise RuntimeError("Portable cell interpolation points changed.")
                    return np.asarray(expected_values, dtype=np.complex128).T

                reconstructed.interpolate(callback, np.asarray([cell], dtype=np.int32))
            reconstructed.x.scatter_forward()
            original = np.asarray(field.x.array[:owned], dtype=np.complex128)
            difference = np.asarray(
                reconstructed.x.array[:owned] - original, dtype=np.complex128
            )
            local_roundtrip_error = max(
                local_roundtrip_error,
                float(
                    np.sqrt(comm.allreduce(float(np.vdot(difference, difference).real)))
                    / max(
                        np.sqrt(comm.allreduce(float(np.vdot(original, original).real))),
                        1.0e-30,
                    )
                ),
            )
        if local_roundtrip_error > 1.0e-12:
            raise AssertionError(
                "MPI8 portable coefficient roundtrip failed: "
                f"measured={local_roundtrip_error:.17e}, "
                "limit=1.00000000000000002e-12."
            )
        result = None
        if comm.rank == 0:
            payload = [item for rank_items in gathered for item in rank_items]
            keys = [tuple(item[0]) for item in payload]
            if len(keys) != len(set(keys)):
                raise RuntimeError("Portable frozen trace cell keys are duplicated.")
            expected_keys = {
                (ix, iy)
                for ix in range(len(cross_section.x_values) - 1)
                for iy in range(len(cross_section.y_values) - 1)
            }
            if set(keys) != expected_keys or len(keys) != 24:
                raise RuntimeError(
                    "Portable frozen trace cell-key coverage mismatch: "
                    f"measured={len(keys)}, expected=24."
                )
            payload.sort(key=lambda item: tuple(item[0]))
            cell_keys = np.asarray([item[0] for item in payload], dtype=np.int64)
            points = np.stack([item[2] for item in payload])
            reference = np.stack([item[3] for item in payload])
            samples = np.transpose(
                np.stack([item[4] for item in payload]), (1, 0, 2, 3)
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                output_path,
                source_raw_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                source_mpi_size=np.asarray(8, dtype=np.int32),
                degree=np.asarray(5, dtype=np.int32),
                schema_version=np.asarray(1, dtype=np.int32),
                z_nm=z_nm,
                cell_keys=cell_keys,
                interpolation_points_xy=points,
                reference_xy=reference,
                Et_cell_interpolation_values=samples,
                mpi8_owned_coefficient_roundtrip_relative_error=np.asarray(
                    local_roundtrip_error, dtype=np.float64
                ),
            )
            result = {
                "path": str(output_path),
                "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
                "cell_count": int(len(cell_keys)),
                "points_per_cell": int(points.shape[1]),
                "mpi8_owned_coefficient_roundtrip_relative_error": float(
                    local_roundtrip_error
                ),
                "roundtrip_scope": "MPI8 raw function -> keyed physical interpolation samples",
            }
        return comm.bcast(result, root=0)
    finally:
        fields.clear()


def _load_portable_frozen_trace_functions(
    archive_path: Path, spaces: Any
) -> tuple[tuple[fem.Function, ...], float]:
    """Rebuild serial trace Functions from portable physical interpolation keys."""

    portable_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    expected_portable_hash = (
        "f55fc4f8f642d580679353e59b5cea2c97460ee14316abac791cd9dd7bd753b3"
    )
    if portable_hash != expected_portable_hash:
        raise RuntimeError(
            "Portable frozen trace hash mismatch: "
            f"measured={portable_hash}, expected={expected_portable_hash}."
        )
    with np.load(archive_path) as archive:
        source_raw_sha256 = str(np.asarray(archive["source_raw_sha256"]).item())
        source_mpi_size = int(np.asarray(archive["source_mpi_size"]).item())
        degree = int(np.asarray(archive["degree"]).item())
        schema_version = int(np.asarray(archive["schema_version"]).item())
        z_nm = np.asarray(archive["z_nm"], dtype=np.float64)
        mpi8_roundtrip = float(
            np.asarray(
                archive["mpi8_owned_coefficient_roundtrip_relative_error"]
            ).item()
        )
        cell_keys = np.asarray(archive["cell_keys"], dtype=np.int64)
        points = np.asarray(
            archive["interpolation_points_xy"], dtype=np.float64
        )
        values = np.asarray(
            archive["Et_cell_interpolation_values"], dtype=np.complex128
        )
    if source_raw_sha256 != (
        "cbae01bfcf983caf29183a6f47a42b1db65f956bc114263cf77ea5182f20711c"
    ) or source_mpi_size != 8 or degree != 5 or schema_version != 1:
        raise RuntimeError("Portable frozen trace metadata contract failed.")
    expected_z_nm = np.arange(10.0, 111.0, 10.0)
    if z_nm.shape != (11,) or not np.allclose(
        z_nm, expected_z_nm, rtol=0.0, atol=1.0e-13
    ):
        raise RuntimeError("Portable frozen trace z-plane metadata is invalid.")
    if not np.isfinite(mpi8_roundtrip) or mpi8_roundtrip > 1.0e-12:
        raise RuntimeError(
            "Portable MPI8 coefficient roundtrip metadata failed: "
            f"measured={mpi8_roundtrip:.17e}, limit=1.00000000000000002e-12."
        )
    if (
        cell_keys.shape != (24, 2)
        or points.ndim != 3
        or values.ndim != 4
        or values.shape[0] != 11
        or values.shape[1] != 24
        or values.shape[2:] != points.shape[1:]
    ):
        raise RuntimeError(
            "Portable frozen trace archive shape contract failed: "
            f"keys={cell_keys.shape}, points={points.shape}, values={values.shape}."
        )
    transverse = spaces.transverse
    mesh = transverse.mesh
    geometry_dofmap = np.asarray(mesh.geometry.dofmap)
    local_cells = np.arange(
        mesh.topology.index_map(mesh.topology.dim).size_local,
        dtype=np.int32,
    )
    x_values = np.unique(np.asarray(mesh.geometry.x[:, 0], dtype=np.float64))
    y_values = np.unique(np.asarray(mesh.geometry.x[:, 1], dtype=np.float64))
    keyed_cells = {
        _portable_cell_key(
            np.mean(mesh.geometry.x[geometry_dofmap[cell], :2], axis=0),
            x_values,
            y_values,
        ): int(cell)
        for cell in local_cells
    }
    if set(map(tuple, cell_keys.tolist())) != set(keyed_cells):
        raise RuntimeError("Portable frozen trace cell keys do not match serial mesh.")
    archive_index = {
        tuple(map(int, key)): index for index, key in enumerate(cell_keys.tolist())
    }
    functions: list[fem.Function] = []
    roundtrip_error = 0.0
    for plane_index, plane_values in enumerate(values):
        field = fem.Function(transverse)
        for cell in local_cells:
            key = _portable_cell_key(
                np.mean(mesh.geometry.x[geometry_dofmap[cell], :2], axis=0),
                x_values,
                y_values,
            )
            cell_index = archive_index.get(key)
            if cell_index is None:
                raise RuntimeError(f"Portable trace cell key is missing: {key}.")
            cell_points = cpp.fem.interpolation_coords(
                transverse.element._cpp_object,
                mesh.geometry._cpp_object,
                np.asarray([cell], dtype=np.int32),
            ).T
            expected_points = points[cell_index]
            if not np.allclose(
                cell_points[:, :2], expected_points, rtol=0.0, atol=1.0e-13
            ):
                raise RuntimeError("Portable serial cell interpolation points mismatch.")
            expected_values = plane_values[cell_index]

            def callback(
                coordinates: np.ndarray,
                expected_points=expected_points,
                expected_values=expected_values,
            ) -> np.ndarray:
                raw_coordinates = np.asarray(coordinates, dtype=np.float64)
                point_matrix = (
                    raw_coordinates.T
                    if raw_coordinates.shape[0] <= 3
                    else raw_coordinates
                )
                if point_matrix.shape[0] != expected_points.shape[0]:
                    raise RuntimeError("Portable serial interpolation point count changed.")
                if not np.allclose(
                    point_matrix[:, :2], expected_points, rtol=0.0, atol=1.0e-13
                ):
                    raise RuntimeError("Portable serial interpolation points changed.")
                return np.asarray(expected_values, dtype=np.complex128).T

            field.interpolate(callback, np.asarray([cell], dtype=np.int32))
        field.x.scatter_forward()
        functions.append(field)
        for key, cell_index in archive_index.items():
            cell = keyed_cells[key]
            cell_points = cpp.fem.interpolation_coords(
                transverse.element._cpp_object,
                mesh.geometry._cpp_object,
                np.asarray([cell], dtype=np.int32),
            ).T
            evaluated = np.asarray(
                field.eval(
                    cell_points,
                    np.full(len(cell_points), cell, dtype=np.int32),
                ),
                dtype=np.complex128,
            )
            roundtrip_error = max(
                roundtrip_error,
                float(
                    np.linalg.norm(evaluated - plane_values[cell_index])
                    / max(
                        np.linalg.norm(plane_values[cell_index]),
                        1.0e-30,
                    )
                ),
            )
    if roundtrip_error > 1.0e-12:
        raise AssertionError(
            "Portable frozen trace interpolation roundtrip failed: "
            f"{roundtrip_error:.17e}, limit=1.00000000000000002e-12."
        )
    return tuple(functions), roundtrip_error


def _realify_hermitian_mass_sparse(
    mass: PETSc.Mat, incoming_gram: np.ndarray
) -> PETSc.Mat:
    """Return sparse ``R(diag(mass, incoming_gram))`` in serial ordering."""

    indptr, indices, values = mass.getValuesCSR()
    cut = sparse.csr_matrix(
        (values, indices, indptr), shape=mass.getSize(), dtype=np.complex128
    )
    base = sparse.block_diag(
        (cut, sparse.csr_matrix(incoming_gram)), format="csr"
    )
    realified = sparse.bmat(
        [[base.real, -base.imag], [base.imag, base.real]], format="csr"
    )
    matrix = PETSc.Mat().createAIJ(
        size=realified.shape,
        csr=(realified.indptr, realified.indices, realified.data),
        comm=PETSc.COMM_SELF,
    )
    matrix.assemble()
    matrix.setOption(PETSc.Mat.Option.SYMMETRIC, True)
    matrix.setOption(PETSc.Mat.Option.SPD, True)
    matrix.convert("seqsbaij")
    matrix.setOption(PETSc.Mat.Option.SYMMETRIC, True)
    matrix.setOption(PETSc.Mat.Option.SPD, True)
    return matrix


def _sample_q5_metric_isotropic_sources(
    rng: np.random.Generator,
    width: int,
    factor: PETSc.Mat,
    realified_metric: PETSc.Mat,
    cut_mass: Any,
    *,
    scale: float,
) -> tuple[np.ndarray, np.ndarray, float, float]:
    """Sample circular-complex source columns with frozen ``G_S`` covariance."""

    gaussian = (
        rng.standard_normal((1248, width))
        + 1.0j * rng.standard_normal((1248, width))
    ) / np.sqrt(2.0)
    rhs = factor.createVecRight()
    solved = factor.createVecLeft()
    forward_solved = factor.createVecLeft()
    full_solved = factor.createVecLeft()
    reconstructed = realified_metric.createVecLeft()
    samples = np.empty_like(gaussian)
    residual_max = 0.0
    imaginary_leakage_max = 0.0
    try:
        for column in range(width):
            rhs.getArray()[:] = np.concatenate(
                (gaussian[:, column].real, gaussian[:, column].imag)
            )
            rhs.assemble()
            factor.solveBackward(rhs, solved)
            factor.solveForward(rhs, forward_solved)
            factor.solveBackward(forward_solved, full_solved)
            realified_metric.mult(full_solved, reconstructed)
            reconstructed.axpy(-1.0, rhs)
            residual_max = max(
                residual_max,
                float(
                    reconstructed.norm() / max(rhs.norm(), 1.0e-30)
                ),
            )
            values = solved.getArray(readonly=True)
            imaginary_leakage_max = max(
                imaginary_leakage_max,
                float(
                    np.max(np.abs(values.imag), initial=0.0)
                    / max(np.linalg.norm(values.real), 1.0e-30)
                ),
            )
            half = values[:1248] + 1.0j * values[1248:]
            samples[:1200, column] = cut_mass.multiply_columns(
                half[:1200]
            )[:, 0]
            samples[1200:, column] = half[1200:]
    finally:
        reconstructed.destroy()
        full_solved.destroy()
        forward_solved.destroy()
        solved.destroy()
        rhs.destroy()
    return scale * samples, gaussian, residual_max, imaginary_leakage_max


def _gc_orthonormalize_block(
    candidate: np.ndarray,
    existing: np.ndarray,
    gc_action: Any,
) -> np.ndarray:
    """Apply two-pass metric reorthogonalization and the frozen rank cutoff."""

    block = np.asarray(candidate, dtype=np.complex128).copy()
    for _ in range(2):
        if existing.shape[1]:
            metric_block = gc_action(block)
            coefficients = np.empty(
                (existing.shape[1], block.shape[1]), dtype=np.complex128
            )
            for start in range(0, existing.shape[1], 16):
                stop = min(start + 16, existing.shape[1])
                basis_block = np.asarray(existing[:, start:stop])
                coefficients[start:stop] = (
                    basis_block.conj().T @ metric_block
                )
            for start in range(0, existing.shape[1], 16):
                stop = min(start + 16, existing.shape[1])
                block -= np.asarray(existing[:, start:stop]) @ coefficients[
                    start:stop
                ]
    gram = block.conj().T @ gc_action(block)
    eigenvalues, vectors = np.linalg.eigh(0.5 * (gram + gram.conj().T))
    keep = eigenvalues > (1.0e-12**2) * eigenvalues[-1]
    return (block @ vectors[:, keep]) / np.sqrt(eigenvalues[keep])


def _gc_projected_orthonormalize_block(
    candidate: np.ndarray,
    existing: np.ndarray,
    gc_action: Any,
    projector: Any,
) -> np.ndarray:
    """Orthonormalize a block while preserving the supplied metric subspace."""

    block = _gc_orthonormalize_block(candidate, existing, gc_action)
    block = projector(block)
    return _gc_orthonormalize_block(block, existing, gc_action)


@dataclass(frozen=True)
class EntityTrace:
    """One edge or face-interior block in original trace numbering."""

    coordinates: np.ndarray
    original_dofs: np.ndarray


@dataclass(frozen=True)
class OrientedBlock:
    """A small entity-local coefficient map, never a global dense matrix."""

    target_original_dofs: np.ndarray
    source_original_dofs: np.ndarray
    coefficients: np.ndarray


@dataclass(frozen=True)
class TracePlaneView:
    """One endpoint trace with global active ids remapped to local ids."""

    original_rows: np.ndarray
    active_global: np.ndarray
    expansion_by_original: Mapping[int, SparseRow]
    root_original_by_local: Mapping[int, int]

    @property
    def active_rows(self) -> int:
        return len(self.active_global)


@dataclass(frozen=True)
class SparsePortTransfer:
    """Block-sparse active port map with primal and Hermitian-dual actions."""

    source_size: int
    target_size: int
    rows: Mapping[int, SparseRow]

    def primal(self, source: np.ndarray) -> np.ndarray:
        source = np.asarray(source, dtype=np.complex128)
        if source.ndim not in (1, 2) or source.shape[0] != self.source_size:
            raise ValueError(
                f"source shape must start with ({self.source_size},), got {source.shape}"
            )
        target_shape = (self.target_size,) if source.ndim == 1 else (
            self.target_size,
            source.shape[1],
        )
        target = np.zeros(target_shape, dtype=np.complex128)
        for row, (columns, values) in self.rows.items():
            target[int(row)] = values @ source[columns]
        return target

    def dual(self, target_dual: np.ndarray) -> np.ndarray:
        """Apply ``J^H`` without materialising ``J``."""

        target_dual = np.asarray(target_dual, dtype=np.complex128)
        if target_dual.ndim not in (1, 2) or target_dual.shape[0] != self.target_size:
            raise ValueError(
                f"target dual shape must start with ({self.target_size},), "
                f"got {target_dual.shape}"
            )
        target_shape = (self.source_size,) if target_dual.ndim == 1 else (
            self.source_size,
            target_dual.shape[1],
        )
        source_dual = np.zeros(target_shape, dtype=np.complex128)
        for row, (columns, values) in self.rows.items():
            if target_dual.ndim == 1:
                source_dual[columns] += values.conj() * target_dual[int(row)]
            else:
                source_dual[columns] += values.conj()[:, None] * target_dual[int(row), :]
        return source_dual


@dataclass(frozen=True)
class LivePlaneSnapshot:
    """Copied endpoint data that remains valid after destroying its system."""

    original_rows: np.ndarray
    active_rows: np.ndarray
    plane: TracePlaneView
    edges: tuple[EntityTrace, ...]
    faces: tuple[EntityTrace, ...]


def _shifted_key(
    coordinates: np.ndarray, z_shift: float, tolerance: float
) -> tuple[tuple[int, int, int], ...]:
    shifted = np.asarray(coordinates, dtype=np.float64).copy()
    shifted[:, 2] += float(z_shift)
    return canonical_entity_key(shifted, tolerance)


def _match_entities_by_z_translation(
    source: Iterable[EntityTrace],
    target: Iterable[EntityTrace],
    *,
    z_shift: float,
    tolerance: float,
) -> tuple[tuple[EntityTrace, EntityTrace], ...]:
    """Match geometry after a z-only shift; x and y remain unchanged."""

    source = tuple(source)
    target = tuple(target)
    source_keys = tuple(
        _shifted_key(entity.coordinates, z_shift, tolerance) for entity in source
    )
    target_keys = tuple(
        canonical_entity_key(entity.coordinates, tolerance) for entity in target
    )
    if len(set(source_keys)) != len(source_keys):
        raise ValueError("source endpoint geometry keys are not unique")
    if len(set(target_keys)) != len(target_keys):
        raise ValueError("target endpoint geometry keys are not unique")
    if set(source_keys) != set(target_keys):
        raise ValueError("source and target endpoint geometry key sets differ")
    target_by_key = dict(zip(target_keys, target, strict=True))
    return tuple(
        (entity, target_by_key[key])
        for entity, key in zip(source, source_keys, strict=True)
    )


def _edge_is_reversed(
    source_coordinates: np.ndarray,
    target_coordinates: np.ndarray,
    z_shift: float,
    tolerance: float,
) -> bool:
    shifted = np.asarray(source_coordinates, dtype=np.float64).copy()
    shifted[:, 2] += float(z_shift)
    target_coordinates = np.asarray(target_coordinates, dtype=np.float64)
    if np.allclose(shifted, target_coordinates, atol=tolerance, rtol=0.0):
        return False
    if np.allclose(shifted[::-1], target_coordinates, atol=tolerance, rtol=0.0):
        return True
    raise ValueError("matched edge vertices do not differ by orientation only")


def build_original_transfer_blocks(
    source_edges: Iterable[EntityTrace],
    target_edges: Iterable[EntityTrace],
    source_faces: Iterable[EntityTrace],
    target_faces: Iterable[EntityTrace],
    *,
    degree: int,
    z_shift: float,
    tolerance: float,
) -> tuple[OrientedBlock, ...]:
    """Build unphased ``Q`` blocks, separating edges from face interiors."""

    blocks: list[OrientedBlock] = []
    for source, target in _match_entities_by_z_translation(
        source_edges, target_edges, z_shift=z_shift, tolerance=tolerance
    ):
        transform = edge_coefficient_transform(
            degree,
            reversed_orientation=_edge_is_reversed(
                source.coordinates,
                target.coordinates,
                z_shift,
                tolerance,
            ),
        )
        blocks.append(
            OrientedBlock(target.original_dofs, source.original_dofs, transform)
        )

    for source, target in _match_entities_by_z_translation(
        source_faces, target_faces, z_shift=z_shift, tolerance=tolerance
    ):
        shifted = np.asarray(source.coordinates, dtype=np.float64).copy()
        shifted[:, 2] += float(z_shift)
        permutation = _face_vertex_permutation(
            np.asarray(target.coordinates, dtype=np.float64), shifted, tolerance
        )
        transform = face_coefficient_transform(degree, permutation)
        blocks.append(
            OrientedBlock(target.original_dofs, source.original_dofs, transform)
        )
    return tuple(blocks)


def _combine_sparse_terms(
    indices: Iterable[int], values: Iterable[complex]
) -> SparseRow:
    combined: dict[int, complex] = {}
    for index, value in zip(indices, values, strict=True):
        combined[int(index)] = combined.get(int(index), 0.0j) + complex(value)
    nonzero = [(index, value) for index, value in combined.items() if value != 0.0]
    return (
        np.asarray([item[0] for item in nonzero], dtype=np.int64),
        np.asarray([item[1] for item in nonzero], dtype=np.complex128),
    )


def _q_c_source_row(
    block: OrientedBlock,
    local_target_row: int,
    source_plane: TracePlaneView,
) -> SparseRow:
    columns: list[int] = []
    values: list[complex] = []
    for local_source, original in enumerate(block.source_original_dofs):
        active, weights = source_plane.expansion_by_original[int(original)]
        coefficient = block.coefficients[local_target_row, local_source]
        columns.extend(int(index) for index in active)
        values.extend(coefficient * np.asarray(weights, dtype=np.complex128))
    return _combine_sparse_terms(columns, values)


def build_primal_transfer(
    blocks: Iterable[OrientedBlock],
    source_plane: TracePlaneView,
    target_plane: TracePlaneView,
) -> SparsePortTransfer:
    """Construct sparse ``J`` satisfying ``C_target J = Q C_source``.

    Each active target coordinate is fixed by its owned representative row.
    Constraint compatibility for all other target originals is checked by the
    dedicated gate, not repaired with a pseudoinverse or interpolation.
    """

    desired_by_target_original: dict[int, SparseRow] = {}
    for block in blocks:
        for local_target, original in enumerate(block.target_original_dofs):
            desired_by_target_original[int(original)] = _q_c_source_row(
                block, local_target, source_plane
            )

    rows: dict[int, SparseRow] = {}
    for local_active, original in target_plane.root_original_by_local.items():
        rows[int(local_active)] = desired_by_target_original[int(original)]
    return SparsePortTransfer(
        source_size=source_plane.active_rows,
        target_size=target_plane.active_rows,
        rows=rows,
    )


def expand_constraints(
    plane: TracePlaneView, active_values: np.ndarray
) -> dict[int, complex]:
    """Apply ``C`` as sparse row actions for gates and fixture integration."""

    active_values = np.asarray(active_values, dtype=np.complex128)
    return {
        int(original): complex(weights @ active_values[active])
        for original, (active, weights) in plane.expansion_by_original.items()
    }


def build_trace_plane_view(
    constraints: TraceConstraintMap,
    endpoint_original: np.ndarray,
    endpoint_active: np.ndarray,
) -> TracePlaneView:
    """Remap one endpoint from global condensed ids to local ``0..1199``."""

    original_rows = np.asarray(endpoint_original, dtype=np.int64)
    active_global = np.asarray(endpoint_active, dtype=np.int64)
    global_to_local = {
        int(global_id): local_id
        for local_id, global_id in enumerate(active_global)
    }
    expansion: dict[int, SparseRow] = {}
    for original in original_rows:
        global_ids, weights = constraints.expansion_by_original[int(original)]
        expansion[int(original)] = (
            np.asarray(
                [global_to_local[int(global_id)] for global_id in global_ids],
                dtype=np.int64,
            ),
            np.asarray(weights, dtype=np.complex128),
        )
    root_by_local: dict[int, int] = {}
    for original in original_rows:
        original = int(original)
        if original not in constraints.original_to_active:
            continue
        global_active = constraints.original_to_active[original]
        if global_active in global_to_local:
            root_by_local[global_to_local[global_active]] = original
    if len(original_rows) != 1250 or len(active_global) != 1200:
        raise AssertionError(
            "endpoint trace must contain 1250 original and 1200 active rows"
        )
    if set(root_by_local) != set(range(1200)):
        raise AssertionError("endpoint active rows do not have local root originals")
    return TracePlaneView(
        original_rows=original_rows,
        active_global=active_global,
        expansion_by_original=expansion,
        root_original_by_local=root_by_local,
    )


def gate_constraint_identity(
    transfer: SparsePortTransfer,
    blocks: Iterable[OrientedBlock],
    source_plane: TracePlaneView,
    target_plane: TracePlaneView,
) -> None:
    """Compare all 1250 sparse rows of ``C_target J`` and ``Q C_source``."""

    def left_row(original: int) -> SparseRow:
        target_active, target_weights = target_plane.expansion_by_original[original]
        columns: list[int] = []
        values: list[complex] = []
        for active, weight in zip(target_active, target_weights, strict=True):
            row_columns, row_values = transfer.rows[int(active)]
            columns.extend(int(value) for value in row_columns)
            values.extend(complex(weight) * row_values)
        return _combine_sparse_terms(columns, values)

    compared = 0
    for block in blocks:
        for local_target, original in enumerate(block.target_original_dofs):
            expected = _q_c_source_row(block, local_target, source_plane)
            actual = left_row(int(original))
            if not _sparse_rows_equal(actual, expected):
                raise AssertionError("C_target J != Q C_source")
            compared += 1
    if compared != 1250:
        raise AssertionError(f"full operator gate compared {compared} rows, not 1250")


def _sparse_rows_equal(
    left: SparseRow, right: SparseRow, tolerance: float = 1.0e-12
) -> bool:
    left_values = dict(zip(left[0].tolist(), left[1].tolist(), strict=True))
    right_values = dict(zip(right[0].tolist(), right[1].tolist(), strict=True))
    keys = set(left_values) | set(right_values)
    return all(
        np.isclose(
            left_values.get(key, 0.0j),
            right_values.get(key, 0.0j),
            atol=tolerance,
            rtol=tolerance,
        )
        for key in keys
    )


def gate_bidirectional_roundtrip(
    forward: SparsePortTransfer,
    reverse: SparsePortTransfer,
) -> None:
    """Gate both sparse operator compositions against their identities."""

    def gate_composition(
        first: SparsePortTransfer, second: SparsePortTransfer
    ) -> None:
        for output_row in range(second.target_size):
            middle_columns, middle_values = second.rows[output_row]
            input_columns: list[int] = []
            input_values: list[complex] = []
            for middle, weight in zip(
                middle_columns, middle_values, strict=True
            ):
                columns, values = first.rows[int(middle)]
                input_columns.extend(int(value) for value in columns)
                input_values.extend(complex(weight) * values)
            composition_row = _combine_sparse_terms(input_columns, input_values)
            identity_row = (
                np.asarray([output_row], dtype=np.int64),
                np.asarray([1.0], dtype=np.complex128),
            )
            if not _sparse_rows_equal(composition_row, identity_row):
                raise AssertionError(
                    "independently constructed sparse roundtrip is not identity"
                )

    gate_composition(forward, reverse)
    gate_composition(reverse, forward)


def gate_dual_pairing(
    transfer: SparsePortTransfer,
    source: np.ndarray,
    target_dual: np.ndarray,
    *,
    tolerance: float = 1.0e-12,
) -> None:
    left = np.vdot(target_dual, transfer.primal(source))
    right = np.vdot(transfer.dual(target_dual), source)
    if not np.allclose(left, right, atol=tolerance, rtol=tolerance):
        raise AssertionError("dual pairing for J^H failed")


def gate_p5_6x4_counts(
    edges: Iterable[EntityTrace],
    faces: Iterable[EntityTrace],
    plane: TracePlaneView,
) -> None:
    edges = tuple(edges)
    faces = tuple(faces)
    actual = (
        sum(len(entity.original_dofs) for entity in edges),
        sum(len(entity.original_dofs) for entity in faces),
        plane.active_rows,
    )
    expected = (290, 960, 1200)
    if actual != expected or actual[0] + actual[1] != 1250:
        raise AssertionError(f"p5 6x4 port counts {actual} != {expected}")
    entity_original = np.concatenate(
        [entity.original_dofs for entity in (*edges, *faces)]
    )
    entity_set = {int(value) for value in entity_original}
    plane_set = {int(value) for value in plane.original_rows}
    if len(entity_set) != len(entity_original):
        raise AssertionError("endpoint entity original DoFs contain duplicates")
    if len(plane_set) != len(plane.original_rows):
        raise AssertionError("endpoint plane original rows contain duplicates")
    if entity_set != plane_set:
        raise AssertionError("endpoint entity and plane original row sets differ")


def _facets_at_z(V: Any, z_nm: float, tolerance: float) -> np.ndarray:
    """Return mesh facets whose ordered geometry lies on one z-plane."""

    msh = V.mesh
    fdim = msh.topology.dim - 1
    msh.topology.create_entities(fdim)
    index_map = msh.topology.index_map(fdim)
    facets = np.arange(
        index_map.size_local + index_map.num_ghosts, dtype=np.int32
    )
    geometry = cpp.mesh.entities_to_geometry(
        msh._cpp_object, fdim, facets, True
    )
    return np.asarray(
        [
            int(facet)
            for facet, geometry_dofs in zip(facets, geometry, strict=True)
            if np.all(
                np.abs(
                    msh.geometry.x[np.asarray(geometry_dofs, dtype=np.int64), 2]
                    - float(z_nm)
                )
                <= tolerance
            )
        ],
        dtype=np.int32,
    )


def _d2_case_descriptor(case_id: str) -> dict[str, Any]:
    """Return the fixed, evidence-bound D2 anchor selection."""

    case_id = str(case_id).upper()
    default_reference = Path(
        "benchmarks/artifacts/task036/"
        "c70ad32e3cb741f382e2cc901e056ae1ea0ba284/"
        "review_v4_one_cell/mpi8_m120_exact_oracle_work/full3d_exact_trace"
    )
    default_hashes = {
        "exact_interface_traces.npz": "cbae01bfcf983caf29183a6f47a42b1db65f956bc114263cf77ea5182f20711c",
        "dtn_port_diffraction_orders_3d.json": "5766b9a5e8d1de4649109d5950bcddc9969d661970f4277fade46196a78176ad",
        "dtn_port_power_metrics_3d.json": "0e49e255b64b724743037ca087cc00883ceab22ab6cd826efc016c998fb2d091",
        "volume_absorption.json": "3665692ec860f159694e6b0a9d1bde3707542d44ae416281f8219c07bc18d194",
    }
    formal_root = Path(
        "benchmarks/artifacts/task036/"
        "6d5e9781bcb1458ecac7a77af22fa2d420f0cd55/v2_robustness"
    )
    formal_hashes = {
        "A001-P": {
            "dtn_port_diffraction_orders_3d.json": "a51592ebce5df5e65f8a31420aceff0867978da2dd07a8312b2d5bf2dd431fb4",
            "dtn_port_power_metrics_3d.json": "bdce575aa96674a9307b472e30b1dc8c5b2b52148a49b85946200a4a95c04b19",
            "volume_absorption.json": "6f063a72e18bb2d483df6162518527d508afd95723a167b49866efef47ea3cbe",
        },
        "A004-P": {
            "dtn_port_diffraction_orders_3d.json": "759db1cd19f79ba70bfd431a5497b8e23999777bebc1f3a9a6167568db536c3d",
            "dtn_port_power_metrics_3d.json": "e05183759d8bb0df39b1a129753a53a5f938a616da62372c40156864f157ed2e",
            "volume_absorption.json": "52a89612f504d3dd64bf2cf20420af72449b609df55b58273095953f47115ae8",
        },
        "A049-P": {
            "dtn_port_diffraction_orders_3d.json": "3b9cdd4cc9e0eeda9fa01d32c9c2a55495cc780bf6a885774d582f11d4b1b999",
            "dtn_port_power_metrics_3d.json": "3435cb9109b6936272022e35328246dd4bb3b65b4a16b0de44fe6f808896ccb2",
            "volume_absorption.json": "e47dbf50f2e64a439156fd6d00f9241bfd27e4f5ae21b13567f2cda53c113603",
        },
    }
    scan_root_9cfeca = Path(
        "benchmarks/artifacts/task036/"
        "9cfeca9e49320f5e82bf009aba19d7c9adbadf23/v2_robustness"
    )
    scan_root_2b56c = Path(
        "benchmarks/artifacts/task036/"
        "2b56c68cae38b92c803c08c2fd28379a8af7f166/v2_robustness"
    )
    scan_hashes = {
        "A002-P": {
            "dtn_port_diffraction_orders_3d.json": "fd3d614361309030d4b079d270905983a54e2d1504393b3b9663d4a6a70b5b6c",
            "dtn_port_power_metrics_3d.json": "af5f73241b3877a363ff68d28067336e0d436d78edf19d7f61e47cd372637702",
            "volume_absorption.json": "0b2f147dc2b24214027e34b2dffe426175d08198e05b145fc61a7a228796b75e",
        },
        "A003-P": {
            "dtn_port_diffraction_orders_3d.json": "121c53be1ffbc00ddfbe0897ee995b9d8fb96a3ffa27188feedd4658cb5c6e02",
            "dtn_port_power_metrics_3d.json": "319631b0ec333827e414a78457486ac8a8911f18f964ae9fd640f878427ac44b",
            "volume_absorption.json": "db1dc62b23fe5cec081d5e2cba2961f0dc0f6d2cc3ccb112a887e66faf34bf71",
        },
        "A007-P": {
            "dtn_port_diffraction_orders_3d.json": "766050dd47bf81b2d26310a5068856346141a79356015849b0754adcc8140471",
            "dtn_port_power_metrics_3d.json": "b6371142abd2fbb804d437089f1cf7fe1faf771d42267218ccc482a86699a88c",
            "volume_absorption.json": "4d2b7d0b1a5810633b751c6aa0a72956c729216945d8c2950cd4dfe56ca5da10",
        },
        "A008-P": {
            "dtn_port_diffraction_orders_3d.json": "394d3763b1ecbaf895a2686744c1d868583002d50f39439a3494b7a73a8b70b1",
            "dtn_port_power_metrics_3d.json": "7c9a74932626a4aa297eb48ad8986ae1d5f30f3dbe469a8102d1df9ad78b87a4",
            "volume_absorption.json": "549702c1860e7f7f68db35bf6605e028990978515c7c8575f9283b29543cef10",
        },
        "A046-P": {
            "dtn_port_diffraction_orders_3d.json": "044a0ad68fa84b57f8f058f7df9ae88fc57999c03df36e3270b8232869c1e671",
            "dtn_port_power_metrics_3d.json": "9ca5062fb72086222b07f333f0d6b4faf5fb024ba7226225dcdd780e9c0e0912",
            "volume_absorption.json": "fbe5cc4fada50a2f5b555360a192400b2ce8bb66129f66864594861030bb6ad6",
        },
    }
    cases = {
        "A004-S": (89.5, 45.0, "s", default_reference, default_hashes),
        "A001-P": (89.5, 0.0, "p", formal_root / "A001-P" / "full3d", formal_hashes["A001-P"]),
        "A004-P": (89.5, 45.0, "p", formal_root / "A004-P" / "full3d", formal_hashes["A004-P"]),
        "A049-P": (80.0, 90.0, "p", formal_root / "A049-P" / "full3d", formal_hashes["A049-P"]),
        "A002-P": (89.5, 15.0, "p", scan_root_9cfeca / "A002-P" / "full3d", scan_hashes["A002-P"]),
        "A003-P": (89.5, 30.0, "p", scan_root_2b56c / "A003-P" / "full3d", scan_hashes["A003-P"]),
        "A007-P": (89.5, 90.0, "p", scan_root_2b56c / "A007-P" / "full3d", scan_hashes["A007-P"]),
        "A008-P": (89.0, 0.0, "p", scan_root_9cfeca / "A008-P" / "full3d", scan_hashes["A008-P"]),
        "A046-P": (80.0, 45.0, "p", scan_root_9cfeca / "A046-P" / "full3d", scan_hashes["A046-P"]),
    }
    if case_id not in cases:
        raise ValueError(f"unsupported D2 case {case_id!r}")
    theta, phi, polarization, reference_root, reference_hashes = cases[case_id]
    cfg = replace(
        _authority_config(),
        case_name=f"task036_{case_id.lower().replace('-', '_')}_direct",
        incident_theta_deg=theta,
        incident_phi_deg=phi,
        polarization_kind=polarization,
    )
    if case_id == "A004-S":
        watchdog_summary = Path(
            "benchmarks/artifacts/task036/6d5e9781bcb1458ecac7a77af22fa2d420f0cd55/"
            "v2_robustness/A004-S/full3d/watchdog_summary.json"
        )
        formal_peak_bytes = 11326935040
        source_equivalence = "equivalent_to_formal_6d5_numeric_reference"
        boundary = {
            "formal_reference": "6d5 A004-S",
            "c70_core_blob_compatibility_gate": "pass",
            "max_channel_complex_amplitude_difference": 7.45546e-14,
            "max_RTA_difference": 6.43e-14,
            "not_same_source_as_final_e7208_and_requires_final_sha_full3d_rerun": True,
        }
        resource_reference = {
            "watchdog_wall_s": float(
                json.loads(watchdog_summary.read_text())[
                    "solver_summary"
                ]["elapsed_seconds"]
            ),
            "process_tree_peak_bytes": formal_peak_bytes,
            "process_tree_peak_gib": formal_peak_bytes / 2**30,
            "swap": 0,
            "resource_baseline_source": "formal_6d5_watchdog",
            "memory_comparison_status": "simultaneous_process_tree_memory_valid",
            "wall_comparison_status": "final_same_sha_same_schedule_rerun_required",
        }
    else:
        watchdog_summary = reference_root / "watchdog_summary.json"
        watchdog = json.loads(watchdog_summary.read_text())
        peak_mb = float(
            watchdog["resource_authority"]["max_process_tree_rss_mb"]
        )
        formal_peak_bytes = int(round(peak_mb * 1024**2))
        if case_id in {"A002-P", "A008-P", "A046-P"}:
            reference_label = "9cfeca9e49320f5e82bf009aba19d7c9adbadf23"
        elif case_id in {"A003-P", "A007-P"}:
            reference_label = "2b56c68cae38b92c803c08c2fd28379a8af7f166"
        else:
            reference_label = "6d5"
        source_equivalence = (
            "formal_6d5_reference"
            if reference_label == "6d5"
            else f"formal_{reference_label}_reference"
        )
        boundary = {
            "formal_reference": f"{reference_label} {case_id}",
            "not_same_source_as_final_e7208_and_requires_final_sha_full3d_rerun": True,
        }
        resource_reference = {
            "watchdog_wall_s": float(
                json.loads(
                    (reference_root / "run_summary.json").read_text()
                )["elapsed_seconds"]
            ),
            "process_tree_peak_bytes": formal_peak_bytes,
            "process_tree_peak_gib": formal_peak_bytes / 2**30,
            "swap": 0,
            "resource_baseline_source": f"formal_{reference_label}_watchdog_simultaneous_process_tree_memory",
            "wall_source": f"formal_{reference_label}_first_parallel_dispatch_openmpi_binding",
            "memory_comparison_status": "simultaneous_process_tree_memory_valid",
            "wall_comparison_status": "historical_parallel_binding_not_final_authority",
        }
    return {
        "case_id": case_id,
        "cfg": cfg,
        "reference_root": reference_root,
        "reference_hashes": reference_hashes,
        "source_equivalence": source_equivalence,
        "source_equivalence_boundary": boundary,
        "resource_reference": resource_reference,
        "output_root": Path("benchmarks/artifacts/task036/direct_d2")
        / case_id.lower(),
    }


def _validate_current_full3d_reference(
    record_path: Path, reference_root: Path, cfg: Any
) -> dict[str, Any]:
    """Validate the explicit current Full3D authority used by D2."""

    record_bytes = record_path.read_bytes()
    record = json.loads(record_bytes)
    if record.get("status") != "full3d_reference_pass":
        raise AssertionError("current Full3D record is not a reference pass")
    qualification = record.get("qualification", {})
    if qualification.get("pass") is not True or qualification.get("failures"):
        raise AssertionError("current Full3D qualification is not clean")
    current_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    if subprocess.check_output(
        ["git", "status", "--short", "--untracked-files=all"], text=True
    ).strip():
        raise AssertionError("current source worktree is dirty")
    source = record.get("source", {})
    if source.get("verified_clean_sha") != current_sha:
        raise AssertionError("current Full3D record SHA is not the current clean SHA")
    summary = record.get("solver_summary", {})
    config = summary.get("config", {})
    config_checks = {
        "degree": (record.get("degree"), cfg.nedelec_degree),
        "h_nm": (record.get("h_nm"), cfg.mesh_target_size),
        "mpi_size": (record.get("mpi_size"), 8),
        "polarization_kind": (record.get("polarization_kind"), cfg.polarization_kind),
        "incident_theta_deg": (
            summary.get("incident_theta_deg"),
            cfg.incident_theta_deg,
        ),
        "incident_phi_deg": (summary.get("incident_phi_deg"), cfg.incident_phi_deg),
        "grating_height_nm": (config.get("grating_height"), cfg.grating_height),
        "grating_width_x_nm": (config.get("grating_width_x"), cfg.grating_width_x),
        "mesh_axis_cell_counts": (
            config.get("mesh_axis_cell_counts"),
            list(cfg.mesh_axis_cell_counts),
        ),
    }
    for key, (observed, expected) in config_checks.items():
        if observed != expected:
            raise AssertionError(
                f"current Full3D physical config mismatch for {key}: "
                f"observed={observed!r}, expected={expected!r}"
            )
    artifact_hashes: dict[str, str] = {}
    for name in (
        "dtn_port_diffraction_orders_3d.json",
        "dtn_port_power_metrics_3d.json",
        "volume_absorption.json",
    ):
        path = reference_root / name
        if not path.is_file():
            raise FileNotFoundError(f"current Full3D reference is missing {path}")
        artifact_hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    if artifact_hashes["dtn_port_diffraction_orders_3d.json"] != record.get(
        "dtn_orders_sha256"
    ):
        raise AssertionError("current diffraction-orders SHA is not record-bound")
    power = json.loads((reference_root / "dtn_port_power_metrics_3d.json").read_text())
    volume = json.loads((reference_root / "volume_absorption.json").read_text())
    for label, payload, keys in (
        (
            "power",
            power,
            "R_total T_total R00_total R_plus_T_plus_A_volume A_volume_total energy_closure_error_port_volume incident_power_code_units".split(),
        ),
        (
            "volume",
            volume,
            "A_volume_total energy_closure_error_port_volume incident_power_code_units".split(),
        ),
    ):
        for key in keys:
            if key not in payload or key not in summary or payload[key] != summary[key]:
                raise AssertionError(
                    f"current Full3D {label} observable mismatch for {key}"
                )
    resource_authority = record.get("resource_authority", {})
    wall_s = summary.get("elapsed_seconds")
    peak_mb = resource_authority.get("max_process_tree_rss_mb")
    swap_mb = resource_authority.get("max_process_tree_swap_mb")
    if wall_s is None or peak_mb is None or swap_mb is None or float(swap_mb) != 0.0:
        raise AssertionError(
            "current Full3D resource authority is incomplete or swapped"
        )
    return {
        "record_sha256": hashlib.sha256(record_bytes).hexdigest(),
        "source_sha": current_sha,
        "artifact_hashes": artifact_hashes,
        "physical_config": {key: pair[0] for key, pair in config_checks.items()},
        "resource_reference": {
            "watchdog_wall_s": float(wall_s),
            "process_tree_peak_bytes": int(round(float(peak_mb) * 1024**2)),
            "process_tree_peak_gib": float(peak_mb) / 1024.0,
            "swap": float(swap_mb),
            "resource_baseline_source": "current_full3d_record",
            "memory_comparison_status": "simultaneous_process_tree_memory_valid",
            "wall_comparison_status": "same_source_record",
        },
    }


def _build_d1_local_factor_setup(
    work_dir: Any,
    case_cfg: Any | None = None,
    endpoint_comms: tuple[Any, Any] | None = None,
) -> dict[str, Any]:
    """Build only the one-cell and two endpoint local action factors."""

    cfg = case_cfg if case_cfg is not None else _authority_config()
    one_cell_cfg = _one_cell_config(cfg)
    one_cell_mesh = build_airbox_mesh_3d(
        one_cell_cfg,
        Path(work_dir.name) / "one_cell_mesh",
    )
    V = _create_nedelec_space(one_cell_mesh.mesh, one_cell_cfg)
    one_cell_floquet = build_double_floquet_mpc(V, one_cell_mesh, one_cell_cfg)
    volume_form, linear_form = _build_variational_forms(
        one_cell_mesh.mesh,
        one_cell_mesh,
        one_cell_cfg,
        V,
        field_formulation="total_field_dtn_port",
    )
    condensed = build_unconstrained_assembly_time_condensation(
        fem.form(volume_form),
        V,
        one_cell_mesh.cell_tags,
        mpc=one_cell_floquet.mpc,
    )
    one_cell_rows = identify_endpoint_active_rows(
        V,
        condensed,
        left_facets=_facets_at_z(V, one_cell_cfg.z_min, 1.0e-10),
        right_facets=_facets_at_z(V, one_cell_cfg.z_max, 1.0e-10),
    )
    cell_action = build_one_cell_two_port_schur_action(
        condensed.matrix, one_cell_rows
    )
    print("heartbeat: D1 local one-cell factor ready", flush=True)
    if endpoint_comms is None:
        endpoint_comms = (MPI.COMM_WORLD, MPI.COMM_WORLD)
    bottom_comm, top_comm = endpoint_comms
    bottom = bottom_rows = bottom_action = None
    top = top_rows = top_action = None
    if bottom_comm != MPI.COMM_NULL:
        bottom = assemble_hybrid_local_dtn_system(
            cfg,
            "bottom",
            bottom_interface_z_nm=10.0,
            top_interface_z_nm=110.0,
            comm=bottom_comm,
        )
        print("heartbeat: D1 local bottom factor ready", flush=True)
        bottom_rows = identify_endpoint_active_rows(
            bottom.V,
            bottom.static_condensation.condensed,
            left_facets=_facets_at_z(bottom.V, -10.0, 1.0e-10),
            right_facets=_facets_at_z(bottom.V, 10.0, 1.0e-10),
        )
        bottom_action = build_hybrid_local_one_sided_schur_action(
            bottom, bottom_rows.right_active, +1.0
        )
    if top_comm != MPI.COMM_NULL:
        top = assemble_hybrid_local_dtn_system(
            cfg,
            "top",
            bottom_interface_z_nm=10.0,
            top_interface_z_nm=110.0,
            comm=top_comm,
        )
        print("heartbeat: D1 local top factor ready", flush=True)
        top_rows = identify_endpoint_active_rows(
            top.V,
            top.static_condensation.condensed,
            left_facets=_facets_at_z(top.V, 110.0, 1.0e-10),
            right_facets=_facets_at_z(top.V, 130.0, 1.0e-10),
        )
        top_action = build_hybrid_local_one_sided_schur_action(
            top, top_rows.left_active, +1.0
        )
    print("heartbeat: D1 local endpoint factors ready", flush=True)
    return {
        "cfg": cfg,
        "one_cell_cfg": one_cell_cfg,
        "one_cell_mesh": one_cell_mesh,
        "V": V,
        "one_cell_floquet": one_cell_floquet,
        "condensed": condensed,
        "volume_form": volume_form,
        "linear_form": linear_form,
        "one_cell_rows": one_cell_rows,
        "cell_action": cell_action,
        "bottom": bottom,
        "top": top,
        "bottom_rows": bottom_rows,
        "top_rows": top_rows,
        "bottom_action": bottom_action,
        "top_action": top_action,
        "endpoint_comms": endpoint_comms,
    }


def run_live_d1a_materialization_timing() -> dict[str, Any]:
    """Time one deterministic 16-column slice after local factors are ready.

    This is deliberately an assembly-time probe: it does not build the trace
    chain, modes, coarse operators, or a global factor.  RSS is reported from
    ``resource.getrusage`` (Linux process peak); no process-tree sampler is
    available in this runner, so that field remains explicitly unavailable.
    """

    def rss_snapshot() -> dict[str, Any]:
        local_peak = int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        )
        return {
            "per_rank_process_lifetime_peak_rss_kib": [
                int(value)
                for value in MPI.COMM_WORLD.allgather(local_peak)
            ],
            "not_simultaneous": True,
            "process_tree_rss": "unavailable",
            "scope": "resource.RUSAGE_SELF.ru_maxrss_linux_peak_per_rank",
        }

    def action_identity(action: Any, input_rows: int) -> dict[str, Any]:
        factor = getattr(action, "factor", None)
        ksp_type = factor.getType() if factor is not None else None
        pc_type = None
        factor_solver_type = None
        if factor is not None and hasattr(factor, "getPC"):
            pc = factor.getPC()
            pc_type = pc.getType()
            factor_solver_type = pc.getFactorSolverType()
        if (
            ksp_type != "preonly"
            or pc_type != "lu"
            or factor_solver_type != "mumps"
        ):
            raise AssertionError(
                "D1a local factor identity requires "
                f"KSP=preonly, PC=lu, factor_solver=mumps; got "
                f"{ksp_type}, {pc_type}, {factor_solver_type}"
            )
        return {
            "action_type": type(action).__name__,
            "input_rows": int(input_rows),
            "ksp_type": ksp_type,
            "pc_type": pc_type,
            "factor_solver_type": factor_solver_type,
        }

    def time_identity_slice(
        action: Any, input_rows: int, output_rows: int
    ) -> dict[str, Any]:
        values = np.zeros((input_rows, 16), dtype=np.complex128)
        values[np.arange(16), np.arange(16)] = 1.0
        apply = getattr(action, "apply_columns", None)
        if apply is None:
            apply = action.apply_trace_columns
        segment_start = time.perf_counter()
        result = np.asarray(apply(values[:, :16]), dtype=np.complex128)
        if result.shape != (output_rows, 16):
            raise AssertionError(
                f"D1a action output shape {result.shape} != ({output_rows}, 16)"
            )
        segment_wall = time.perf_counter() - segment_start
        comm = MPI.COMM_WORLD
        segment_wall = comm.allreduce(segment_wall, op=MPI.MAX)
        return {
            "input_rows": int(input_rows),
            "output_rows": int(output_rows),
            "slice_columns": 16,
            "segment_wall_s": float(segment_wall),
            "average_column_wall_s": float(segment_wall / 16.0),
            "per_rank_process_lifetime_peak_rss_kib": rss_snapshot()[
                "per_rank_process_lifetime_peak_rss_kib"
            ],
            "action": action_identity(action, input_rows),
        }

    work_dir = tempfile.TemporaryDirectory(prefix="task036-d1a-")
    cell_action = bottom_action = top_action = None
    condensed = None
    one_cell_floquet = None
    bottom = top = None
    rss_start = rss_snapshot()
    try:
        setup = _build_d1_local_factor_setup(work_dir)
        cell_action = setup["cell_action"]
        bottom_action = setup["bottom_action"]
        top_action = setup["top_action"]
        condensed = setup["condensed"]
        one_cell_floquet = setup["one_cell_floquet"]
        bottom = setup["bottom"]
        top = setup["top"]
        MPI.COMM_WORLD.Barrier()

        segments = {
            "cell": time_identity_slice(cell_action, 2400, 2400),
            "bottom": time_identity_slice(bottom_action, 1200, 1200),
            "top": time_identity_slice(top_action, 1200, 1200),
        }
        extrapolated = {
            "cell_columns": 2400,
            "bottom_columns": 1200,
            "top_columns": 1200,
            "total_columns": 4800,
            "method": "16-column identity-slice wall linearly scaled by column count",
        }
        extrapolated["cell_wall_s"] = segments["cell"]["segment_wall_s"] * 150.0
        extrapolated["bottom_wall_s"] = segments["bottom"]["segment_wall_s"] * 75.0
        extrapolated["top_wall_s"] = segments["top"]["segment_wall_s"] * 75.0
        extrapolated["estimated_total_wall_s"] = sum(
            extrapolated[key]
            for key in ("cell_wall_s", "bottom_wall_s", "top_wall_s")
        )
        return {
            "status": "measured_direct_d1a_materialization_timing",
            "stage": "local_factors_ready_then_batched_16_slice",
            "mpi_size": int(MPI.COMM_WORLD.size),
            "slice_columns": 16,
            "segments": segments,
            "linear_extrapolation": extrapolated,
            "rss": {"start": rss_start, "end": rss_snapshot()},
            "internal_discrete_bloch_qep": "not_run",
            "external_dtn_modes": "assembled_required",
            "full_forward_rhs_solve": "not_run",
            "coarse_overlap_fgmres": "not_run",
            "q5_c2_recovery": "not_run",
            "global_dense_formed": False,
            "global_mumps_factor": "not_run",
            "scalar_route_threshold_wall_s": 1200.0,
            "threshold_policy": "above 20 minutes use existing KSP.matSolve multi-RHS next",
        }
    finally:
        for action in (cell_action, bottom_action, top_action):
            if action is not None:
                action.destroy()
        if condensed is not None:
            condensed.destroy()
        if one_cell_floquet is not None and hasattr(one_cell_floquet.mpc, "destroy"):
            one_cell_floquet.mpc.destroy()
        if bottom is not None:
            bottom.destroy()
        if top is not None:
            top.destroy()
        work_dir.cleanup()


def _build_d1_trace_chain(setup: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    """Build the D1b/D1c trace chain and its three sparse transfers."""

    from src.solvers.hybrid_trace_chain import FullFeTraceChainAction

    V = setup["V"]
    condensed = setup["condensed"]
    one_cell_rows = setup["one_cell_rows"]
    one_cell_mesh = setup["one_cell_mesh"]
    one_cell_cfg = setup["one_cell_cfg"]
    bottom = setup["bottom"]
    top = setup["top"]
    bottom_rows = setup["bottom_rows"]
    top_rows = setup["top_rows"]
    one_cell_left = build_trace_plane_view(
        condensed.trace_constraints,
        one_cell_rows.left_original,
        one_cell_rows.left_active,
    )
    one_cell_right = build_trace_plane_view(
        condensed.trace_constraints,
        one_cell_rows.right_original,
        one_cell_rows.right_active,
    )
    one_cell_left_edges, one_cell_left_faces = entity_traces_from_live_space(
        V,
        degree=5,
        plane_facets=one_cell_mesh.facet_tags.find(one_cell_cfg.tags.z_min),
    )
    one_cell_right_edges, one_cell_right_faces = entity_traces_from_live_space(
        V,
        degree=5,
        plane_facets=one_cell_mesh.facet_tags.find(one_cell_cfg.tags.z_max),
    )

    def endpoint_plane(
        system: Any,
        rows: Any,
        side: str,
    ) -> tuple[TracePlaneView, tuple[EntityTrace, ...], tuple[EntityTrace, ...]]:
        if side == "bottom":
            original, active, z_nm = rows.right_original, rows.right_active, 10.0
        else:
            original, active, z_nm = rows.left_original, rows.left_active, 110.0
        plane = build_trace_plane_view(
            system.static_condensation.condensed.trace_constraints,
            original,
            active,
        )
        edges, faces = entity_traces_from_live_space(
            system.V,
            degree=5,
            plane_facets=_facets_at_z(system.V, z_nm, 1.0e-10),
        )
        return plane, edges, faces

    bottom_plane = bottom_edges = bottom_faces = None
    top_plane = top_edges = top_faces = None
    if bottom is not None:
        bottom_plane, bottom_edges, bottom_faces = endpoint_plane(
            bottom, bottom_rows, "bottom"
        )
    if top is not None:
        top_plane, top_edges, top_faces = endpoint_plane(top, top_rows, "top")
    jc, _, _, _ = build_bidirectional_transfers(
        one_cell_left_edges,
        one_cell_right_edges,
        one_cell_left_faces,
        one_cell_right_faces,
        one_cell_left,
        one_cell_right,
        degree=5,
        z_shift=10.0,
        tolerance=1.0e-8,
    )
    endpoint_comms = setup.get("endpoint_comms")
    if endpoint_comms is not None and any(
        comm != MPI.COMM_WORLD for comm in endpoint_comms
    ):
        from src.solvers.hybrid_trace_chain import (
            FullFeTraceChainAction,
            PairedEndpointSchurAction,
        )

        bottom_transfer = bottom_reverse = None
        top_transfer = top_reverse = None
        if bottom is not None:
            bottom_transfer, bottom_reverse, _, _ = build_bidirectional_transfers(
                one_cell_left_edges,
                bottom_edges,
                one_cell_left_faces,
                bottom_faces,
                one_cell_left,
                bottom_plane,
                degree=5,
                z_shift=10.0,
                tolerance=1.0e-8,
            )
        if top is not None:
            top_transfer, top_reverse, _, _ = build_bidirectional_transfers(
                one_cell_left_edges,
                top_edges,
                one_cell_left_faces,
                top_faces,
                one_cell_left,
                top_plane,
                degree=5,
                z_shift=110.0,
                tolerance=1.0e-8,
            )
        paired = PairedEndpointSchurAction(
            setup.get("bottom_action"),
            bottom_transfer,
            0,
            setup.get("top_action"),
            top_transfer,
            4,
        )
        chain = FullFeTraceChainAction(
            setup["cell_action"],
            jc,
            paired_endpoints=paired,
        )
        setup["endpoint_bundles"] = {
            "bottom": {
                "action": setup.get("bottom_action"),
                "transfer": bottom_transfer,
                "reverse_transfer": bottom_reverse,
                "comm": endpoint_comms[0],
                "root": 0,
                "system": bottom,
            },
            "top": {
                "action": setup.get("top_action"),
                "transfer": top_transfer,
                "reverse_transfer": top_reverse,
                "comm": endpoint_comms[1],
                "root": 4,
                "system": top,
            },
        }
        setup["bottom_action"] = None
        setup["top_action"] = None
        return chain, jc, bottom_transfer, top_transfer
    jb, jb_reverse, _, _ = build_bidirectional_transfers(
        one_cell_left_edges,
        bottom_edges,
        one_cell_left_faces,
        bottom_faces,
        one_cell_left,
        bottom_plane,
        degree=5,
        z_shift=10.0,
        tolerance=1.0e-8,
    )
    jt, jt_reverse, _, _ = build_bidirectional_transfers(
        one_cell_left_edges,
        top_edges,
        one_cell_left_faces,
        top_faces,
        one_cell_left,
        top_plane,
        degree=5,
        z_shift=110.0,
        tolerance=1.0e-8,
    )
    chain = FullFeTraceChainAction(
        setup["cell_action"],
        jc,
        setup["bottom_action"],
        jb,
        setup["top_action"],
        jt,
    )
    for key in ("cell_action", "bottom_action", "top_action"):
        setup[key] = None
    setup["d1_endpoint_transfers"] = {
        "bottom": (jb, jb_reverse),
        "top": (jt, jt_reverse),
    }
    return chain, jc, jb, jt


def _build_d1_actual_rhs(
    bottom: Any,
    top: Any,
    bottom_action: Any,
    top_action: Any,
    chain: Any,
    jb: Any,
    jt: Any,
) -> tuple[np.ndarray, dict[str, Any], np.ndarray, np.ndarray]:
    """Build the selected direct-case endpoint RHS in canonical trace rows."""

    plane_size = int(chain.plane_size)
    bottom_rhs_values = bottom_action._replicated_values(bottom.b)
    top_rhs_values = top_action._replicated_values(top.b)
    bottom_direct = bottom_action.condense_rhs_columns(
        bottom_rhs_values[:, None]
    )[:, 0]
    top_direct = top_action.condense_rhs_columns(
        top_rhs_values[:, None]
    )[:, 0]
    top_b_norm = float(np.linalg.norm(top_rhs_values))
    bottom_b_norm = float(np.linalg.norm(bottom_rhs_values))
    if not np.isfinite(top_b_norm) or top_b_norm <= 1.0e-30:
        raise AssertionError(
            f"D1 top assembled RHS invalid: top_b_norm={top_b_norm:.17e}."
        )
    if not np.isfinite(bottom_b_norm) or bottom_b_norm > 1.0e-10:
        raise AssertionError(
            f"D1 bottom assembled RHS invalid: bottom_b_norm={bottom_b_norm:.17e}."
        )
    actual_rhs = np.zeros((chain.global_size, 1), dtype=np.complex128)
    actual_rhs[:plane_size, 0] = jb.dual(bottom_direct)
    actual_rhs[-plane_size:, 0] = jt.dual(top_direct)
    if not np.all(np.isfinite(actual_rhs)):
        raise AssertionError("D1 actual RHS is not finite.")
    rhs_norm = float(np.linalg.norm(actual_rhs))
    if rhs_norm <= 1.0e-30:
        raise AssertionError("D1 actual RHS is zero.")
    return actual_rhs, {
        "source_identity": "assembled_top_b_from_case_cfg",
        "top_b_norm": top_b_norm,
        "bottom_b_norm": bottom_b_norm,
        "rhs_norm": rhs_norm,
    }, bottom_rhs_values, top_rhs_values


def _build_d2_mpi_endpoint_rhs(
    setup: Mapping[str, Any], chain: Any
) -> tuple[
    np.ndarray,
    dict[str, Any],
    np.ndarray | None,
    np.ndarray | None,
]:
    """Condense endpoint RHS on MPI4 sides and share canonical vectors."""

    comm = MPI.COMM_WORLD
    plane_size = int(chain.plane_size)
    local_side = "bottom" if comm.rank < 4 else "top"
    bundle = setup["endpoint_bundles"][local_side]
    action = bundle["action"]
    system = bundle["system"]
    transfer = bundle["transfer"]
    values = np.asarray(action._replicated_values(system.b), dtype=np.complex128)
    direct = action.condense_rhs_columns(values[:, None])[:, 0]
    canonical = np.asarray(transfer.dual(direct), dtype=np.complex128)
    bundle["rhs_values"] = values
    local_payload = {
        "canonical": canonical,
        "norm": float(np.linalg.norm(values)),
    }
    bottom_payload = comm.bcast(
        local_payload if comm.rank == 0 else None, root=0
    )
    top_payload = comm.bcast(
        local_payload if comm.rank == 4 else None, root=4
    )
    canonical_by_side = {
        "bottom": np.asarray(bottom_payload["canonical"], dtype=np.complex128),
        "top": np.asarray(top_payload["canonical"], dtype=np.complex128),
    }
    bottom_local = values if local_side == "bottom" else None
    top_local = values if local_side == "top" else None
    bottom_b_norm = float(bottom_payload["norm"])
    top_b_norm = float(top_payload["norm"])
    if not np.isfinite(top_b_norm) or top_b_norm <= 1.0e-30:
        raise AssertionError(f"D2 top assembled RHS invalid: {top_b_norm:.17e}.")
    if not np.isfinite(bottom_b_norm) or bottom_b_norm > 1.0e-10:
        raise AssertionError(f"D2 bottom assembled RHS invalid: {bottom_b_norm:.17e}.")
    actual_rhs = np.zeros((chain.global_size, 1), dtype=np.complex128)
    actual_rhs[:plane_size, 0] = canonical_by_side["bottom"]
    actual_rhs[-plane_size:, 0] = canonical_by_side["top"]
    rhs_norm = float(np.linalg.norm(actual_rhs))
    if not np.all(np.isfinite(actual_rhs)) or rhs_norm <= 1.0e-30:
        raise AssertionError("D2 MPI endpoint RHS is invalid.")
    return actual_rhs, {
        "source_identity": "assembled_top_b_from_case_cfg_mpi4_endpoints",
        "top_b_norm": top_b_norm,
        "bottom_b_norm": bottom_b_norm,
        "rhs_norm": rhs_norm,
    }, bottom_local, top_local


def _run_stage2c_recovery_observables(
    *,
    setup: Mapping[str, Any],
    chain: Any,
    jc: Any,
    jb: Any,
    jt: Any,
    solution: np.ndarray,
    actual_rhs: np.ndarray,
    trace_relative: float,
    rhs_record: Mapping[str, Any],
    bottom_rhs_values: np.ndarray | None,
    top_rhs_values: np.ndarray | None,
    work_dir: Any,
    reference_root: Path | None = None,
    reference_hashes: Mapping[str, str] | None = None,
    output_root: Path | None = None,
    source_equivalence: str = "equivalent_to_formal_6d5_numeric_reference",
    source_equivalence_boundary: Mapping[str, Any] | None = None,
    resource_reference: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the shared direct-trace recovery/observable seam.

    The D2 entry point first uses this narrow seam; the existing C2 path is
    migrated to the same seam as its recovery body is extracted.  Keeping the
    physical recovery in one call site prevents the direct and historical
    paths from silently diverging.
    """

    bottom = setup["bottom"]
    top = setup["top"]
    endpoint_bundles = setup.get("endpoint_bundles")
    if endpoint_bundles is None:
        bottom_action = chain.bottom_action
        top_action = chain.top_action
    else:
        bottom_action = endpoint_bundles["bottom"]["action"]
        top_action = endpoint_bundles["top"]["action"]
    cfg = setup["cfg"]
    trace = np.asarray(solution, dtype=np.complex128)
    if not np.isfinite(trace_relative) or trace_relative > 1.0e-10:
        raise AssertionError(
            "D2 shared recovery trace residual failed: "
            f"{trace_relative:.17e} > 1e-10"
        )
    planes = trace.reshape(11, chain.plane_size)
    def endpoint_complement_residual(
        action: Any,
        trace_values: np.ndarray,
        rhs_values: np.ndarray,
        recovered: np.ndarray,
    ) -> float:
        trace_vec = action.A_HH.createVecRight()
        comp_vec = action.A_cc.createVecRight()
        coupled_vec = action.A_cc.createVecLeft()
        diagonal_vec = action.A_cc.createVecLeft()
        try:
            trace_first, trace_last = map(int, trace_vec.getOwnershipRange())
            trace_vec.getArray()[:] = np.asarray(
                trace_values[trace_first:trace_last], dtype=PETSc.ScalarType
            )
            trace_vec.assemble()
            comp_first, comp_last = map(int, comp_vec.getOwnershipRange())
            comp_vec.getArray()[:] = np.asarray(
                recovered[action.complement_indices[comp_first:comp_last]],
                dtype=PETSc.ScalarType,
            )
            comp_vec.assemble()
            action.A_cH.mult(trace_vec, coupled_vec)
            action.A_cc.mult(comp_vec, diagonal_vec)
            coupled = action._replicated_values(coupled_vec)
            diagonal = action._replicated_values(diagonal_vec)
            target = rhs_values[action.complement_indices]
            return float(
                np.linalg.norm(diagonal + coupled - target)
                / max(
                    np.linalg.norm(coupled),
                    np.linalg.norm(diagonal),
                    np.linalg.norm(target),
                    1.0e-30,
                )
            )
        finally:
            diagonal_vec.destroy()
            coupled_vec.destroy()
            comp_vec.destroy()
            trace_vec.destroy()

    def state_vec(system: Any, values: np.ndarray) -> PETSc.Vec:
        vector = system.A.createVecRight()
        first, last = map(int, vector.getOwnershipRange())
        vector.getArray()[:] = np.asarray(
            values[first:last], dtype=PETSc.ScalarType
        )
        vector.assemble()
        return vector

    def recover_endpoint_side(
        side: str,
        system: Any,
        action: Any,
        transfer: Any,
        canonical_plane: np.ndarray,
        rhs_values: np.ndarray,
        comm: Any,
    ) -> dict[str, Any]:
        trace_values = transfer.primal(canonical_plane)
        recovered = action.recover_augmented_columns(
            trace_values[:, None], rhs_values[:, None]
        )[:, 0]
        payload: dict[str, Any] = {
            "complement": endpoint_complement_residual(
                action, trace_values, rhs_values, recovered
            )
        }
        state = state_vec(system, recovered)
        full_rhs = system.full_fe_rhs.duplicate()
        system.full_fe_rhs.copy(full_rhs)
        try:
            payload["auxiliary"] = _gather_auxiliary_values(
                state, system.n_fe, system.n_external_aux, comm
            )
            payload["power"] = _port_power_metrics(
                cfg,
                system.external_modes,
                payload["auxiliary"],
                system.incident_projections,
            )
            payload["orders"] = _external_diffraction_order_rows(
                cfg,
                (system,),
                (payload["auxiliary"],),
                incident_power=float(payload["power"]["incident_power_code_units"]),
            )
            _add_external_tractions(system, full_rhs, state)
            field, x_fe, _ = _assign_fe_solution_from_assembly_time_condensation(
                state,
                system.static_condensation.condensed,
                system.floquet_data,
                full_rhs,
            )
            try:
                residual = _assembly_time_full_operator_residual(
                    system.bilinear_form,
                    system.floquet_data,
                    x_fe,
                    system.A,
                    system.b,
                    state,
                    system.static_condensation.condensed,
                    full_rhs,
                )
                payload["eliminated"] = float(
                    residual["eliminated_cell_interior_max_abs_residual"]
                )
                payload["direct"] = _auxiliary_direct_tangential_projection_audit(
                    field,
                    system.external_modes,
                    payload["auxiliary"],
                    system.incident_projections,
                    system.local_mesh.mesh_data,
                    cfg,
                    quadrature_degree=system.dtn_quadrature_degree,
                )
                volume_cfg = (
                    cfg
                    if side == "bottom"
                    else replace(
                        cfg,
                        z_min=float(system.local_mesh.z_values[0]),
                        z_max=float(system.local_mesh.z_values[-1]),
                    )
                )
                volume = compute_volume_absorption_3d(
                    system.local_mesh.mesh_data,
                    volume_cfg,
                    field,
                    Path(work_dir.name) / f"d2_{side}_volume",
                    incident_power=float(payload["power"]["incident_power_code_units"]),
                )
                payload["volume"] = float(volume["A_volume_total"])
            finally:
                x_fe.destroy()
                del field
        finally:
            full_rhs.destroy()
            state.destroy()
        return payload

    if endpoint_bundles is None:
        bottom_payload = recover_endpoint_side(
            "bottom", bottom, bottom_action, jb, planes[0], bottom_rhs_values, MPI.COMM_WORLD
        )
        top_payload = recover_endpoint_side(
            "top", top, top_action, jt, planes[-1], top_rhs_values, MPI.COMM_WORLD
        )
        payloads = {"bottom": bottom_payload, "top": top_payload}
    else:
        local_side = "bottom" if MPI.COMM_WORLD.rank < 4 else "top"
        bundle = endpoint_bundles[local_side]
        local_transfer = bundle["transfer"]
        local_plane = planes[0] if local_side == "bottom" else planes[-1]
        local_rhs = bottom_rhs_values if local_side == "bottom" else top_rhs_values
        local_payload = recover_endpoint_side(
            local_side,
            bundle["system"],
            bundle["action"],
            local_transfer,
            local_plane,
            local_rhs,
            bundle["comm"],
        )
        payloads = {
            "bottom": MPI.COMM_WORLD.bcast(
                local_payload if MPI.COMM_WORLD.rank == 0 else None, root=0
            ),
            "top": MPI.COMM_WORLD.bcast(
                local_payload if MPI.COMM_WORLD.rank == 4 else None, root=4
            ),
        }
    bottom_payload = payloads["bottom"]
    top_payload = payloads["top"]
    bottom_auxiliary = np.asarray(bottom_payload["auxiliary"])
    top_auxiliary = np.asarray(top_payload["auxiliary"])
    actual_power = dict(top_payload["power"])
    actual_power["T_total"] = float(bottom_payload["power"]["T_total"])
    actual_power["T_total_dtn_port_modal"] = float(
        bottom_payload["power"]["T_total_dtn_port_modal"]
    )
    for key in (
        "dtn_port_mode_count",
        "dtn_port_top_mode_count",
        "dtn_port_bottom_mode_count",
        "dtn_port_propagating_mode_count",
        "dtn_port_rayleigh_warning_count",
    ):
        actual_power[key] = sum(
            int(payloads[side]["power"][key]) for side in ("bottom", "top")
        )
    actual_power["R_plus_T"] = float(
        actual_power["R_total"] + actual_power["T_total"]
    )
    actual_power["R_plus_T_dtn_port_modal"] = float(
        actual_power["R_total_dtn_port_modal"]
        + actual_power["T_total_dtn_port_modal"]
    )
    actual_power["A_balance"] = float(1.0 - actual_power["R_plus_T"])
    actual_power["A_balance_dtn_port_modal"] = float(
        1.0 - actual_power["R_plus_T_dtn_port_modal"]
    )
    actual_power["incident_power_code_units"] = float(
        bottom_payload["power"]["incident_power_code_units"]
    )
    actual_orders = []
    for side in ("bottom", "top"):
        for row in payloads[side]["orders"]:
            copied = dict(row)
            copied["auxiliary_index"] = len(actual_orders)
            actual_orders.append(copied)
    endpoint_direct = {
        side: payloads[side]["direct"] for side in ("bottom", "top")
    }
    endpoint_volumes = {
        side: float(payloads[side]["volume"]) for side in ("bottom", "top")
    }
    complement = {
        side: float(payloads[side]["complement"]) for side in ("bottom", "top")
    }
    endpoint_eliminated = max(
        float(bottom_payload["eliminated"]), float(top_payload["eliminated"])
    )
    if max(complement.values()) > 1.0e-9:
        raise AssertionError(
            "D2 endpoint complement Gate failed: "
            f"measured={complement}, limit=1.00000000000000006e-09"
        )
    artifact_root = reference_root or Path(
        "benchmarks/artifacts/task036/"
        "c70ad32e3cb741f382e2cc901e056ae1ea0ba284/"
        "review_v4_one_cell/mpi8_m120_exact_oracle_work/full3d_exact_trace"
    )
    artifact_files = dict(reference_hashes or {
        "exact_interface_traces.npz": "cbae01bfcf983caf29183a6f47a42b1db65f956bc114263cf77ea5182f20711c",
        "dtn_port_diffraction_orders_3d.json": "5766b9a5e8d1de4649109d5950bcddc9969d661970f4277fade46196a78176ad",
        "dtn_port_power_metrics_3d.json": "0e49e255b64b724743037ca087cc00883ceab22ab6cd826efc016c998fb2d091",
        "volume_absorption.json": "3665692ec860f159694e6b0a9d1bde3707542d44ae416281f8219c07bc18d194",
    })
    artifact_hashes = {
        name: hashlib.sha256((artifact_root / name).read_bytes()).hexdigest()
        for name in artifact_files
    }
    for name, expected in artifact_files.items():
        if artifact_hashes[name] != expected:
            raise AssertionError(
                f"D2 reference artifact hash mismatch for {name}: "
                f"measured={artifact_hashes[name]}, expected={expected}"
            )
    from benchmarks.analyze_task036_robustness_scan import (
        _compare_channels,
        _order_map,
        _significance_inventory,
    )

    frozen_orders = json.loads(
        (artifact_root / "dtn_port_diffraction_orders_3d.json").read_text(
            encoding="utf-8"
        )
    )
    frozen_map = _order_map(frozen_orders["orders"], "frozen")
    expected_channel_count = len(frozen_map)
    candidate_rows = []
    for row in actual_orders:
        copied = dict(row)
        amplitude = complex(copied["outgoing_amplitude_at_boundary"])
        copied["outgoing_amplitude_at_boundary"] = [
            float(amplitude.real),
            float(amplitude.imag),
        ]
        candidate_rows.append(copied)
    candidate_map = _order_map(candidate_rows, "candidate")
    significance = _significance_inventory((frozen_map, candidate_map))
    channel_comparison = _compare_channels(
        frozen_map, candidate_map, significance, str(cfg.polarization_kind)
    )
    channel_key_set_equal = set(frozen_map) == set(candidate_map)
    if (
        not channel_key_set_equal
        or channel_comparison["fixed_channel_count"] != expected_channel_count
        or not channel_comparison["pass"]
    ):
        raise AssertionError(
            "D2 reference-channel Gate failed: "
            f"keys_equal={channel_key_set_equal}, "
            f"count={channel_comparison['fixed_channel_count']}, "
            f"expected={expected_channel_count}, "
            f"pass={channel_comparison['pass']}"
        )
    frozen_power = json.loads(
        (artifact_root / "dtn_port_power_metrics_3d.json").read_text(
            encoding="utf-8"
        )
    )
    incident_power_relative = float(
        abs(
            float(actual_power["incident_power_code_units"])
            - float(frozen_power["incident_power_code_units"])
        )
        / max(abs(float(frozen_power["incident_power_code_units"])), 1.0e-30)
    )
    if incident_power_relative > 1.0e-12:
        raise AssertionError(
            "D2 incident power code-unit mismatch: "
            f"measured={incident_power_relative:.17e}, limit=1e-12"
        )
    power_deltas = {
        key: abs(float(actual_power[key]) - float(frozen_power[key]))
        for key in ("R_total", "T_total")
    }
    r00 = {
        key: float(actual_power[key])
        for key in ("R00_s", "R00_p", "R00_total")
        if key in actual_power
    }
    condensed = setup["condensed"]
    one_cell_floquet = setup["one_cell_floquet"]
    one_cell_mesh = setup["one_cell_mesh"]
    one_cell_cfg = setup["one_cell_cfg"]
    volume_form = setup["volume_form"]
    linear_form = setup["linear_form"]
    cell_action = chain.cell_action
    full_zero_rhs = _assemble_unconstrained_vector(linear_form)
    if float(full_zero_rhs.norm()) > 1.0e-12:
        full_zero_rhs.destroy()
        raise AssertionError("D2 one-cell full zero RHS is not zero")
    zero_reduced_rhs = condensed.matrix.createVecLeft()
    zero_reduced_rhs.set(0.0)
    zero_reduced_rhs.assemble()
    axial_residuals: list[float] = []
    eliminated_max = endpoint_eliminated
    core_volumes: list[float] = []
    try:
        for cell_index in range(chain.cell_count):
            cell_port = np.r_[
                planes[cell_index], jc.primal(planes[cell_index + 1])
            ]
            recovered = cell_action.recover_homogeneous_columns(cell_port)[:, 0]
            port_vec = cell_action.A_pp.createVecRight()
            coupled_vec = cell_action.A_ip.createVecLeft()
            interior_vec = cell_action.A_ii.createVecRight()
            diagonal_vec = cell_action.A_ii.createVecLeft()
            try:
                first, last = map(int, port_vec.getOwnershipRange())
                port_vec.getArray()[:] = cell_port[first:last]
                port_vec.assemble()
                cell_action.A_ip.mult(port_vec, coupled_vec)
                interior_values = recovered[cell_action.interior_active]
                first, last = map(int, interior_vec.getOwnershipRange())
                interior_vec.getArray()[:] = interior_values[first:last]
                interior_vec.assemble()
                cell_action.A_ii.mult(interior_vec, diagonal_vec)
                coupled = cell_action._replicated_values(coupled_vec)
                diagonal = cell_action._replicated_values(diagonal_vec)
                axial_residuals.append(
                    float(
                        np.linalg.norm(coupled + diagonal)
                        / max(
                            np.linalg.norm(coupled),
                            np.linalg.norm(diagonal),
                            1.0e-30,
                        )
                    )
                )
            finally:
                diagonal_vec.destroy()
                coupled_vec.destroy()
                interior_vec.destroy()
                port_vec.destroy()
            state = condensed.matrix.createVecRight()
            first, last = map(int, state.getOwnershipRange())
            state.getArray()[:] = recovered[first:last]
            state.assemble()
            field, x_fe, _ = _assign_fe_solution_from_assembly_time_condensation(
                state, condensed, one_cell_floquet, full_zero_rhs
            )
            try:
                residual = _assembly_time_full_operator_residual(
                    volume_form,
                    one_cell_floquet,
                    x_fe,
                    condensed.matrix,
                    zero_reduced_rhs,
                    state,
                    condensed,
                    full_zero_rhs,
                )
                eliminated_max = max(
                    eliminated_max,
                    float(residual["eliminated_cell_interior_max_abs_residual"]),
                )
                volume = compute_volume_absorption_3d(
                    one_cell_mesh,
                    one_cell_cfg,
                    field,
                    Path(work_dir.name) / "d2_core_volume",
                    incident_power=float(actual_power["incident_power_code_units"]),
                )
                core_volumes.append(float(volume["A_volume_total"]))
            finally:
                x_fe.destroy()
                del field
                state.destroy()
    finally:
        zero_reduced_rhs.destroy()
        full_zero_rhs.destroy()
    eliminated_max = max(eliminated_max, endpoint_eliminated)
    direct_counts = {side: len(record["orders"]) for side, record in endpoint_direct.items()}
    direct_max = max(
        float(record["max_absolute_outgoing_projection_difference"])
        for record in endpoint_direct.values()
    )
    direct_pass = (
        sum(direct_counts.values()) == expected_channel_count
        and all(
            count == expected_channel_count // 2
            for count in direct_counts.values()
        )
        and all(record["pass"] is True for record in endpoint_direct.values())
        and direct_max <= 1.0e-10
    )
    volume_total = float(sum(core_volumes) + sum(endpoint_volumes.values()))
    volume_path = artifact_root / "volume_absorption.json"
    volume_hash = hashlib.sha256(volume_path.read_bytes()).hexdigest()
    volume_reference = json.loads(volume_path.read_text(encoding="utf-8"))
    if float(volume_reference["incident_power_code_units"]) != float(
        frozen_power["incident_power_code_units"]
    ):
        raise AssertionError("D2 reference incident power metadata mismatch")
    frozen_volume = float(volume_reference["A_volume_total"])
    closure = float(
        float(actual_power["R_total"])
        + float(actual_power["T_total"])
        + volume_total
        - 1.0
    )
    deltas = {
        "R_total": float(power_deltas["R_total"]),
        "T_total": float(power_deltas["T_total"]),
        "A_volume": abs(volume_total - frozen_volume),
    }
    if (
        max(axial_residuals, default=0.0) > 1.0e-9
        or eliminated_max > 1.0e-9
        or not direct_pass
        or abs(closure) > 1.0e-5
        or max(deltas.values()) > 1.0e-4
    ):
        raise AssertionError(
            "D2 recovery Gate failed: "
            f"axial={max(axial_residuals, default=0.0):.17e}, "
            f"eliminated={eliminated_max:.17e}, direct={direct_pass}, "
            f"closure={closure:.17e}, deltas={deltas}"
        )
    artifact_path = (output_root or Path("benchmarks/artifacts/task036/direct_d2")) / (
        "recovery_observables_full_v1.npz"
    )
    artifact_sha = None
    if MPI.COMM_WORLD.rank == 0:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        amplitudes = np.asarray(
            [complex(row["outgoing_amplitude_at_boundary"]) for row in actual_orders],
            dtype=np.complex128,
        )
        np.savez(
            artifact_path,
            bottom_auxiliary=bottom_auxiliary,
            top_auxiliary=top_auxiliary,
            channel_amplitudes=amplitudes,
            trace_solution=trace[:, 0],
        )
        artifact_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    artifact_sha = MPI.COMM_WORLD.bcast(artifact_sha, root=0)
    rta_deltas = power_deltas
    return {
        "trace_true_residual": trace_relative,
        "trace_true_residual_limit": 1.0e-10,
        "actual_rhs": dict(rhs_record),
        "endpoint_complement": complement,
        "actual_power": dict(actual_power),
        "actual_orders_count": len(actual_orders),
        "reference_artifact_root": str(artifact_root),
        "reference_artifact_hashes": artifact_hashes,
        "source_equivalence": source_equivalence,
        "source_equivalence_boundary": dict(source_equivalence_boundary or {
            "formal_reference": "6d5 A004-S",
            "c70_core_blob_compatibility_gate": "pass",
            "max_channel_complex_amplitude_difference": 7.45546e-14,
            "max_RTA_difference": 6.43e-14,
            "not_same_source_as_final_e7208_and_requires_final_sha_full3d_rerun": True,
        }),
        "resource_reference_6d5": dict(resource_reference or {
            "watchdog_wall_s": 869.607,
            "process_tree_peak_gib": 10.441,
            "swap": 0,
            "resource_baseline_source": "formal_6d5_watchdog",
        }),
        "incident_power_relative": incident_power_relative,
        "channel_key_set_equal": channel_key_set_equal,
        "channel_comparison": channel_comparison,
        "RTA_deltas": deltas,
        "R00": r00,
        "recovery_artifact": {
            "path": str(artifact_path),
            "sha256": artifact_sha,
        },
        "axial_residual_by_cell": axial_residuals,
        "axial_residual": max(axial_residuals, default=0.0),
        "eliminated_cell_interior": eliminated_max,
        "A_volume": volume_total,
        "frozen_A_volume": frozen_volume,
        "energy_closure": closure,
        "endpoint_A_volume": endpoint_volumes,
        "core_A_volume_by_cell": core_volumes,
        "channels": {
            "count": int(channel_comparison["fixed_channel_count"]),
            "expected_count_from_reference": int(expected_channel_count),
            "key_set_equal": channel_key_set_equal,
            "pass": bool(channel_comparison["pass"]),
        },
        "direct_tangential_projection": {
            "count": sum(direct_counts.values()),
            "per_side": {
                side: {
                    "count": direct_counts[side],
                    "max_absolute_outgoing_projection_difference": float(
                        record["max_absolute_outgoing_projection_difference"]
                    ),
                    "pass": bool(record["pass"]),
                }
                for side, record in endpoint_direct.items()
            },
            "max": direct_max,
            "pass": direct_pass,
        },
        "RTA": {
            "R_total_delta": float(rta_deltas["R_total"]),
            "T_total_delta": float(rta_deltas["T_total"]),
            "A_volume_delta": float(deltas["A_volume"]),
            "energy_closure": float(closure),
            "pass": bool(max(deltas.values()) <= 1.0e-4 and abs(closure) <= 1.0e-5),
        },
        "volume_reference_sha256": volume_hash,
        "recovery_observables_complete": True,
    }


def run_live_d1b_assemble_only() -> dict[str, Any]:
    """Assemble the explicit 13200-row trace AIJ and check one probe."""

    work_dir = tempfile.TemporaryDirectory(prefix="task036-d1b-")
    setup: dict[str, Any] | None = None
    chain = None
    matrix = None
    explicit_record: dict[str, Any] = {}
    try:
        setup_start = time.perf_counter()
        setup = _build_d1_local_factor_setup(work_dir)
        local_setup_wall = MPI.COMM_WORLD.allreduce(
            time.perf_counter() - setup_start,
            op=MPI.MAX,
        )
        chain, _jc, _jb, _jt = _build_d1_trace_chain(setup)
        assembly_start = time.perf_counter()
        matrix, explicit_record = chain.build_explicit_trace_matrix(
            column_block_size=16,
            comm=PETSc.COMM_WORLD,
        )
        assembly_wall = MPI.COMM_WORLD.allreduce(
            time.perf_counter() - assembly_start,
            op=MPI.MAX,
        )
        expected_nnz = 31 * 1200**2
        info_sum = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
        info_max = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_MAX)
        mallocs = int(info_sum.get("mallocs", 0.0))
        explicit_record.update(
            {
                "local_setup_wall_s": float(local_setup_wall),
                "assembly_wall_s": float(assembly_wall),
                "expected_stored_nnz": expected_nnz,
                "mat_info_global_sum": {
                    "nz_used": int(info_sum.get("nz_used", 0.0)),
                    "nz_allocated": int(info_sum.get("nz_allocated", 0.0)),
                    "nz_unneeded": int(info_sum.get("nz_unneeded", 0.0)),
                    "mallocs": mallocs,
                    "assemblies": int(info_sum.get("assemblies", 0.0)),
                    "factor_mallocs": int(
                        info_sum.get("factor_mallocs", 0.0)
                    ),
                },
                "mat_info_global_max": {
                    "memory": float(info_max.get("memory", 0.0)),
                    "mallocs": int(info_max.get("mallocs", 0.0)),
                },
            }
        )
        if (
            explicit_record["rows"] != 13200
            or explicit_record["stored_nnz"] != expected_nnz
            or explicit_record["allocated_nnz"] != expected_nnz
            or explicit_record["mat_info_global_sum"]["nz_used"]
            != expected_nnz
            or explicit_record["mat_info_global_sum"]["nz_allocated"]
            != expected_nnz
            or explicit_record["matrix_type"] != "mpiaij"
            or explicit_record["comm_size"] != 8
            or mallocs != 0
        ):
            raise AssertionError(f"D1b explicit AIJ Gate failed: {explicit_record}")

        x = matrix.createVecRight()
        y_action = matrix.createVecLeft()
        y = matrix.createVecLeft()
        try:
            first, last = map(int, x.getOwnershipRange())
            global_index = np.arange(first, last, dtype=np.float64)
            x.getArray()[:] = np.sin(0.013 * (global_index + 1.0)) + 1j * np.cos(
                0.017 * (global_index + 1.0)
            )
            x.assemble()
            action_start = time.perf_counter()
            chain.mult(None, x, y_action)
            action_wall = MPI.COMM_WORLD.allreduce(
                time.perf_counter() - action_start,
                op=MPI.MAX,
            )
            kx_start = time.perf_counter()
            matrix.mult(x, y)
            kx_wall = MPI.COMM_WORLD.allreduce(
                time.perf_counter() - kx_start,
                op=MPI.MAX,
            )
            local_gap = np.asarray(y.getArray(readonly=True)) - np.asarray(
                y_action.getArray(readonly=True)
            )
            local_y = np.asarray(y_action.getArray(readonly=True))
            comm = MPI.COMM_WORLD
            gap_norm = float(
                np.sqrt(comm.allreduce(float(np.vdot(local_gap, local_gap).real)))
            )
            action_norm = float(
                np.sqrt(comm.allreduce(float(np.vdot(local_y, local_y).real)))
            )
            max_abs_gap = comm.allreduce(
                float(np.max(np.abs(local_gap))), op=MPI.MAX
            )
        finally:
            y.destroy()
            y_action.destroy()
            x.destroy()
        kx_relative = gap_norm / max(action_norm, 1.0e-30)
        if not np.isfinite(kx_relative) or kx_relative > 1.0e-11:
            raise AssertionError(
                f"D1b Kx equivalence {kx_relative:.6e} exceeds 1e-11"
            )
        explicit_record.update(
            {
                "kx_relative_error": float(kx_relative),
                "kx_gate_limit": 1.0e-11,
                "kx_wall_s": float(kx_wall),
                "reference_action_wall_s": float(action_wall),
                "kx_max_abs_gap": float(max_abs_gap),
                "global_dense_formed": False,
            }
        )
        chain.destroy()
        chain = None
        matrix.destroy()
        matrix = None
        return {
            "status": "partial_pass_direct_d1b_assemble_only",
            "stage": "trace_aij_assembled_kx_checked_then_destroyed",
            "comm_size": 8,
            "explicit_trace": explicit_record,
            "global_factor": "not_run",
            "global_solve": "not_run",
            "external_dtn_modes": "assembled_as_part_of_endcaps",
            "internal_discrete_bloch_qep": "not_run",
            "coarse": "not_run",
            "overlap": "not_run",
            "fgmres": "not_run",
            "q5": "not_run",
            "c2": "not_run",
            "watchdog": {
                "command": "benchmarks/run_task033_case090_watchdog.py",
                "scope": "external process-tree peak and swap authority",
                "status": "development_dirty_tree_fail_closed",
                "runner_sampling": "not_added",
            },
        }
    finally:
        if chain is not None:
            chain.destroy()
        if matrix is not None:
            matrix.destroy()
        if setup is not None:
            for key in ("cell_action", "bottom_action", "top_action"):
                action = setup.get(key)
                if action is not None:
                    action.destroy()
            condensed = setup.get("condensed")
            if condensed is not None:
                condensed.destroy()
            one_cell_floquet = setup.get("one_cell_floquet")
            if one_cell_floquet is not None and hasattr(
                one_cell_floquet.mpc, "destroy"
            ):
                one_cell_floquet.mpc.destroy()
            for key in ("bottom", "top"):
                system = setup.get(key)
                if system is not None:
                    system.destroy()
        work_dir.cleanup()


def run_live_d1c_direct_factor_solve() -> dict[str, Any]:
    """Factor the formal trace AIJ and solve the single A004-S RHS."""

    comm = MPI.COMM_WORLD
    if comm.size != 8:
        raise AssertionError("Direct-D1c requires MPI8.")
    work_dir = tempfile.TemporaryDirectory(prefix="task036-d1c-")
    setup: dict[str, Any] | None = None
    chain = matrix = rhs = solution = ksp = None
    residual = None
    artifact_path: Path | None = None
    try:
        setup = _build_d1_local_factor_setup(work_dir)
        bottom = setup["bottom"]
        top = setup["top"]
        bottom_action = setup["bottom_action"]
        top_action = setup["top_action"]
        chain, jc, jb, jt = _build_d1_trace_chain(setup)

        actual_rhs, rhs_record, _bottom_rhs_values, _top_rhs_values = _build_d1_actual_rhs(
            bottom,
            top,
            bottom_action,
            top_action,
            chain,
            jb,
            jt,
        )
        rhs_norm = rhs_record["rhs_norm"]

        matrix, explicit_record = chain.build_explicit_trace_matrix(
            column_block_size=16,
            comm=PETSc.COMM_WORLD,
        )
        expected_nnz = 31 * 1200**2
        info_sum = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
        mallocs = int(info_sum.get("mallocs", 0.0))
        explicit_record.update(
            {
                "expected_stored_nnz": expected_nnz,
                "mat_info_global_sum": {
                    "nz_used": int(info_sum.get("nz_used", 0.0)),
                    "nz_allocated": int(info_sum.get("nz_allocated", 0.0)),
                    "mallocs": mallocs,
                },
            }
        )
        if (
            explicit_record["rows"] != 13200
            or explicit_record["stored_nnz"] != expected_nnz
            or explicit_record["allocated_nnz"] != expected_nnz
            or explicit_record["matrix_type"] != "mpiaij"
            or explicit_record["comm_size"] != 8
            or int(info_sum.get("nz_used", 0.0)) != expected_nnz
            or int(info_sum.get("nz_allocated", 0.0)) != expected_nnz
            or mallocs != 0
            or explicit_record.get("global_dense_formed", False)
        ):
            raise AssertionError(
                f"D1c explicit AIJ Gate failed: {explicit_record}"
            )
        rows = int(explicit_record["rows"])
        chain.destroy()
        chain = None
        for key in ("bottom", "top"):
            system = setup.get(key)
            if system is not None:
                system.destroy()
                setup[key] = None
        condensed = setup.get("condensed")
        if condensed is not None:
            condensed.destroy()
            setup["condensed"] = None
        one_cell_floquet = setup.get("one_cell_floquet")
        if one_cell_floquet is not None and hasattr(
            one_cell_floquet.mpc, "destroy"
        ):
            one_cell_floquet.mpc.destroy()
            setup["one_cell_floquet"] = None
        setup.clear()
        setup = None
        bottom = None
        top = None
        bottom_action = None
        top_action = None
        _jc = None
        jb = None
        jt = None
        condensed = None
        one_cell_floquet = None
        system = None
        comm.Barrier()
        print("heartbeat: local_objects_released_before_global_factor", flush=True)

        rhs = matrix.createVecLeft()
        solution = matrix.createVecRight()
        rhs_first, rhs_last = map(int, rhs.getOwnershipRange())
        rhs.getArray()[:] = actual_rhs[rhs_first:rhs_last, 0]
        rhs.assemble()
        ksp = PETSc.KSP().create(PETSc.COMM_WORLD)
        ksp.setOperators(matrix)
        ksp.setType("preonly")
        pc = ksp.getPC()
        pc.setType("lu")
        pc.setFactorSolverType("mumps")
        ksp.setErrorIfNotConverged(True)
        factor_start = time.perf_counter()
        ksp.setUp()
        factor_setup_wall = comm.allreduce(
            time.perf_counter() - factor_start, op=MPI.MAX
        )
        factor_solver_type = pc.getFactorSolverType()
        if (
            ksp.getType() != "preonly"
            or pc.getType() != "lu"
            or factor_solver_type != "mumps"
        ):
            raise AssertionError(
                "D1c factor identity failed: "
                f"ksp={ksp.getType()}, pc={pc.getType()}, "
                f"factor_solver={factor_solver_type}"
            )
        solve_start = time.perf_counter()
        ksp.solve(rhs, solution)
        solve_wall = comm.allreduce(
            time.perf_counter() - solve_start, op=MPI.MAX
        )
        reason = int(ksp.getConvergedReason())
        iterations = int(ksp.getIterationNumber())
        reported_residual = float(ksp.getResidualNorm())
        if reason <= 0:
            raise AssertionError(f"D1c KSP did not converge: reason={reason}")
        residual = matrix.createVecLeft()
        matrix.mult(solution, residual)
        local_gap = np.asarray(residual.getArray(readonly=True)) - np.asarray(
            rhs.getArray(readonly=True)
        )
        local_rhs = np.asarray(rhs.getArray(readonly=True))
        gap_sq = comm.allreduce(float(np.vdot(local_gap, local_gap).real))
        rhs_sq = comm.allreduce(float(np.vdot(local_rhs, local_rhs).real))
        true_residual = float(np.sqrt(gap_sq / max(rhs_sq, 1.0e-300)))
        if not np.isfinite(true_residual) or true_residual > 1.0e-10:
            raise AssertionError(
                f"D1c true residual {true_residual:.17e} exceeds 1e-10"
            )
        local_solution = np.array(solution.getArray(readonly=True), copy=True)
        solution_first, solution_last = map(
            int, solution.getOwnershipRange()
        )
        gathered = comm.gather(
            (solution_first, solution_last, local_solution), root=0
        )
        artifact_sha = None
        artifact_path = Path(
            "benchmarks/artifacts/task036/direct_d1c/trace_solution.npz"
        )
        if comm.rank == 0:
            trace_solution = np.empty(rows, dtype=np.complex128)
            for owned_first, owned_last, values in gathered:
                trace_solution[int(owned_first) : int(owned_last)] = values
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(
                artifact_path,
                trace_solution=trace_solution,
                rhs_norm=np.asarray(rhs_norm),
                true_residual=np.asarray(true_residual),
                rows=np.asarray(rows, dtype=np.int32),
                physical_identity=np.asarray(
                    ["A004-S", "p5-h10", "grazing-0.5deg", "azimuth-45deg"]
                ),
            )
            artifact_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        artifact_sha = comm.bcast(artifact_sha, root=0)
        return {
            "status": "partial_pass_direct_d1c_factor_solve",
            "stage": "formal_trace_aij_global_mumps_factor_single_rhs",
            "comm_size": 8,
            "explicit_trace": explicit_record,
            "factor_setup_wall_s": float(factor_setup_wall),
            "solve_wall_s": float(solve_wall),
            "ksp_reason": reason,
            "ksp_iterations": iterations,
            "reported_residual": reported_residual,
            "true_residual": true_residual,
            "true_residual_limit": 1.0e-10,
            "factor_identity": {
                "ksp_type": ksp.getType(),
                "pc_type": pc.getType(),
                "factor_solver_type": factor_solver_type,
            },
            "source_provenance": {
                "source_identity": rhs_record["source_identity"],
                "top_b_norm": rhs_record["top_b_norm"],
                "bottom_b_norm": rhs_record["bottom_b_norm"],
                "actual_rhs_norm": rhs_norm,
            },
            "trace_solution_artifact": {
                "path": str(artifact_path),
                "sha256": artifact_sha,
            },
            "recovery": "not_run",
            "channels_96": "not_run",
            "RTA": "not_run",
            "direct_vs_full3d": "not_run",
            "global_dense_formed": False,
            "global_factor": "completed",
            "global_solve": "completed",
        }
    finally:
        if ksp is not None:
            ksp.destroy()
        if residual is not None:
            residual.destroy()
        if solution is not None:
            solution.destroy()
        if rhs is not None:
            rhs.destroy()
        if matrix is not None:
            matrix.destroy()
        if chain is not None:
            chain.destroy()
        if setup is not None:
            for key in ("cell_action", "bottom_action", "top_action"):
                action = setup.get(key)
                if action is not None:
                    action.destroy()
            condensed = setup.get("condensed")
            if condensed is not None:
                condensed.destroy()
            one_cell_floquet = setup.get("one_cell_floquet")
            if one_cell_floquet is not None and hasattr(
                one_cell_floquet.mpc, "destroy"
            ):
                one_cell_floquet.mpc.destroy()
            for key in ("bottom", "top"):
                system = setup.get(key)
                if system is not None:
                    system.destroy()
        work_dir.cleanup()


def run_live_d2_block_direct_solve(
    case_id: str = "A004-S",
    *,
    mpi_endpoints: bool = False,
    current_full3d_record: Path | None = None,
    current_full3d_reference_root: Path | None = None,
    d2_output_root: Path | None = None,
) -> dict[str, Any]:
    """Solve one fixed D2 anchor by exact recursive block LU."""

    comm = MPI.COMM_WORLD
    if comm.size != 8:
        raise AssertionError("D2 block-direct solve requires MPI8.")
    endpoint_comms = None
    endpoint_subcomm: Any = None
    if mpi_endpoints:
        side_color = 0 if comm.rank < 4 else 1
        endpoint_subcomm = comm.Split(side_color, comm.rank)
        endpoint_comms = (
            (endpoint_subcomm, MPI.COMM_NULL)
            if side_color == 0
            else (MPI.COMM_NULL, endpoint_subcomm)
        )
    run_start = time.perf_counter()
    case = _d2_case_descriptor(case_id)
    case_id = case["case_id"]
    current_identity: dict[str, Any] | None = None
    current_args = (
        current_full3d_record,
        current_full3d_reference_root,
        d2_output_root,
    )
    if any(value is not None for value in current_args) and not all(
        value is not None for value in current_args
    ):
        raise ValueError(
            "current Full3D D2 mode requires record, reference root, and output root"
        )
    if current_full3d_record is not None:
        current_identity = _validate_current_full3d_reference(
            current_full3d_record,
            current_full3d_reference_root,
            case["cfg"],
        )
        case["reference_root"] = current_full3d_reference_root.resolve()
        case["reference_hashes"] = current_identity["artifact_hashes"]
        case["resource_reference"] = current_identity["resource_reference"]
        case["source_equivalence"] = "current_full3d_same_sha"
        case["source_equivalence_boundary"] = {
            "current_full3d_record": str(current_full3d_record.resolve()),
            "current_full3d_record_sha256": current_identity["record_sha256"],
            "verified_clean_sha": current_identity["source_sha"],
            "physical_config": current_identity["physical_config"],
        }
    if d2_output_root is not None:
        d2_output_root = d2_output_root.resolve()
        if d2_output_root.exists():
            raise FileExistsError(
                f"refusing to overwrite existing D2 output root {d2_output_root}"
            )
        case["output_root"] = d2_output_root
    output_root = Path(case["output_root"])
    work_dir = tempfile.TemporaryDirectory(prefix="task036-d2-")
    setup: dict[str, Any] | None = None
    chain = None
    solution: np.ndarray | None = None
    try:
        setup_start = time.perf_counter()
        setup = _build_d1_local_factor_setup(
            work_dir, case["cfg"], endpoint_comms=endpoint_comms
        )
        local_setup_wall = comm.allreduce(
            time.perf_counter() - setup_start,
            op=MPI.MAX,
        )
        bottom = setup["bottom"]
        top = setup["top"]
        bottom_action = setup["bottom_action"]
        top_action = setup["top_action"]
        chain, jc, jb, jt = _build_d1_trace_chain(setup)
        materialization_start = time.perf_counter()
        compact_blocks, compact_record = chain.build_compact_trace_blocks(
            column_block_size=16
        )
        materialization_wall = comm.allreduce(
            time.perf_counter() - materialization_start,
            op=MPI.MAX,
        )
        block_bytes = int(sum(block.nbytes for block in compact_blocks.values()))
        rhs_start = time.perf_counter()
        if mpi_endpoints:
            actual_rhs, rhs_record, bottom_rhs_values, top_rhs_values = (
                _build_d2_mpi_endpoint_rhs(setup, chain)
            )
        else:
            actual_rhs, rhs_record, bottom_rhs_values, top_rhs_values = (
                _build_d1_actual_rhs(
                    bottom,
                    top,
                    bottom_action,
                    top_action,
                    chain,
                    jb,
                    jt,
                )
            )
        actual_rhs_wall = comm.allreduce(
            time.perf_counter() - rhs_start,
            op=MPI.MAX,
        )
        if actual_rhs.shape != (chain.global_size, 1):
            raise AssertionError(
                f"D2 actual RHS shape {actual_rhs.shape} is not "
                f"({chain.global_size}, 1)."
            )
        diagonal = (
            compact_blocks["bottom_diagonal"],
        ) + (compact_blocks["middle_diagonal"],) * 9 + (
            compact_blocks["top_diagonal"],
        )
        lower = (compact_blocks["lower"],) * 10
        upper = (compact_blocks["upper"],) * 10
        from src.solvers.hybrid_trace_chain import (
            solve_block_tridiagonal_recursive_mpi,
        )

        block_factor_solve_start = time.perf_counter()
        solution, solver_record = solve_block_tridiagonal_recursive_mpi(
            diagonal,
            lower,
            upper,
            tuple(actual_rhs.reshape(11, chain.plane_size, 1)),
            comm=comm,
        )
        block_factor_solve_wall = comm.allreduce(
            time.perf_counter() - block_factor_solve_start,
            op=MPI.MAX,
        )
        compact_blocks = None
        diagonal = lower = upper = None
        residual_start = time.perf_counter()
        residual = chain.apply_columns(solution) - actual_rhs
        residual_relative = float(
            np.linalg.norm(residual)
            / max(np.linalg.norm(actual_rhs), 1.0e-30)
        )
        residual_relative = float(comm.allreduce(residual_relative, op=MPI.MAX))
        residual_wall = comm.allreduce(
            time.perf_counter() - residual_start,
            op=MPI.MAX,
        )
        if not np.isfinite(residual_relative) or residual_relative > 1.0e-10:
            raise AssertionError(
                f"D2 full true residual {residual_relative:.17e} exceeds 1e-10"
            )
        recovery_start = time.perf_counter()
        recovery_record = _run_stage2c_recovery_observables(
            setup=setup,
            chain=chain,
            jc=jc,
            jb=jb,
            jt=jt,
            solution=solution,
            actual_rhs=actual_rhs,
            trace_relative=residual_relative,
            rhs_record=rhs_record,
            bottom_rhs_values=bottom_rhs_values,
            top_rhs_values=top_rhs_values,
            work_dir=work_dir,
            reference_root=case["reference_root"],
            reference_hashes=case["reference_hashes"],
            output_root=output_root,
            source_equivalence=case["source_equivalence"],
            source_equivalence_boundary=case["source_equivalence_boundary"],
            resource_reference=case["resource_reference"],
        )
        recovery_wall = comm.allreduce(
            time.perf_counter() - recovery_start,
            op=MPI.MAX,
        )
        artifact_sha = None
        artifact_path = output_root / "trace_solution_full_v1.npz"
        if comm.rank == 0:
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(
                artifact_path,
                trace_solution=solution[:, 0],
                rhs_norm=np.asarray(rhs_record["rhs_norm"]),
                true_residual=np.asarray(residual_relative),
                rows=np.asarray(chain.global_size, dtype=np.int32),
                physical_identity=np.asarray(
                    [
                        case_id,
                        "p5-h10",
                        f"theta-{case['cfg'].incident_theta_deg}-deg",
                        f"azimuth-{case['cfg'].incident_phi_deg}-deg",
                        str(case["cfg"].polarization_kind),
                    ]
                ),
            )
            artifact_sha = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        artifact_sha = comm.bcast(artifact_sha, root=0)
        total_wall = comm.allreduce(
            time.perf_counter() - run_start,
            op=MPI.MAX,
        )
        result_status = f"pass_direct_hybrid_{case_id.lower().replace('-', '_')}"
        direct_vs_full3d = {
            "reference_root": recovery_record["reference_artifact_root"],
            "artifact_hashes": recovery_record["reference_artifact_hashes"],
            "source_equivalence": recovery_record["source_equivalence"],
            "channel_count": recovery_record["channels"]["count"],
            "channel_key_set_equal": recovery_record["channels"][
                "key_set_equal"
            ],
            "channels_pass": recovery_record["channels"]["pass"],
            "direct_projection_pass": recovery_record[
                "direct_tangential_projection"
            ]["pass"],
            "incident_power_gate_pass": recovery_record[
                "incident_power_relative"
            ] <= 1.0e-12,
            "RTA_deltas": recovery_record["RTA_deltas"],
            "RTA_pass": recovery_record["RTA"]["pass"],
        }
        result = {
            "status": result_status,
            "stage": "compact_blocks_recursive_lu_mpi_column_sharded_direct",
            "endpoint_execution": (
                "paired_mpi4_subcommunicators" if mpi_endpoints else "world_mpi8"
            ),
            "comm_size": 8,
            "local_setup_wall_s": float(local_setup_wall),
            "materialization_wall_s": float(materialization_wall),
            "actual_rhs_wall_s": float(actual_rhs_wall),
            "block_factor_solve_wall_s": float(block_factor_solve_wall or 0.0),
            "residual_wall_s": float(residual_wall),
            "recovery_wall_s": float(recovery_wall),
            "total_wall_s": float(total_wall),
            "compact_blocks": compact_record,
            "five_block_bytes": block_bytes,
            "block_solver": solver_record,
            "actual_rhs": rhs_record,
            "true_residual": residual_relative,
            "true_residual_limit": 1.0e-10,
            "recovery_observables": recovery_record,
            "trace_solution_artifact": {
                "path": str(artifact_path),
                "sha256": artifact_sha,
            },
            "result_artifact": {
                "path": str(output_root / "d2_result_full_v1.json"),
            },
            "global_aij_formed": False,
            "global_mumps": "not_run",
            "krylov_fgmres_pc": "not_run",
            "case_id": case_id,
            "case_descriptor": {
                "incident_theta_deg": float(case["cfg"].incident_theta_deg),
                "incident_phi_deg": float(case["cfg"].incident_phi_deg),
                "polarization_kind": str(case["cfg"].polarization_kind),
                "reference_root": str(case["reference_root"]),
                "resource_reference": case["resource_reference"],
            },
            "channels": recovery_record["channels"],
            "RTA": recovery_record["RTA"],
            "direct_vs_full3d": direct_vs_full3d,
            "final_current_source_same_sha_status": (
                "verified_current_full3d_record_same_sha"
                if current_identity is not None
                else "not_run_requires_final_sha_full3d_rerun"
            ),
            "current_full3d_identity": current_identity,
        }
        result_json_path = output_root / "d2_result_full_v1.json"
        result_json_sha = None
        if comm.rank == 0:
            result_json_path.parent.mkdir(parents=True, exist_ok=True)
            result_json_path.write_text(
                json.dumps(result, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            result_json_sha = hashlib.sha256(
                result_json_path.read_bytes()
            ).hexdigest()
        result_json_sha = comm.bcast(result_json_sha, root=0)
        result["result_artifact"] = {
            "path": str(result_json_path),
            "sha256": result_json_sha,
        }
        return result
    finally:
        if chain is not None:
            chain.destroy()
        if setup is not None:
            for key in ("bottom", "top"):
                system = setup.get(key)
                if system is not None:
                    system.destroy()
            condensed = setup.get("condensed")
            if condensed is not None:
                condensed.destroy()
            one_cell_floquet = setup.get("one_cell_floquet")
            if one_cell_floquet is not None and hasattr(
                one_cell_floquet.mpc, "destroy"
            ):
                one_cell_floquet.mpc.destroy()
        work_dir.cleanup()
        if endpoint_subcomm is not None and endpoint_subcomm != MPI.COMM_NULL:
            endpoint_subcomm.Free()


def entity_traces_from_live_space(
    V: Any,
    *,
    degree: int,
    plane_facets: np.ndarray | None = None,
    z_plane: float | None = None,
    tolerance: float = 1.0e-10,
) -> tuple[tuple[EntityTrace, ...], tuple[EntityTrace, ...]]:
    """Extract ordered edge and face-interior traces on one z-plane."""

    msh = V.mesh
    if (plane_facets is None) == (z_plane is None):
        raise ValueError("provide exactly one of plane_facets or z_plane")
    fdim = msh.topology.dim - 1
    msh.topology.create_entities(1)
    msh.topology.create_entities(fdim)
    facet_map = msh.topology.index_map(fdim)
    all_facets = np.arange(
        facet_map.size_local + facet_map.num_ghosts, dtype=np.int32
    )
    if plane_facets is None:
        facet_geometry = cpp.mesh.entities_to_geometry(
            msh._cpp_object, fdim, all_facets, True
        )
        selected_facets = [
            int(facet)
            for facet, geometry_dofs in zip(
                all_facets, facet_geometry, strict=True
            )
            if np.all(
                np.abs(
                    msh.geometry.x[np.asarray(geometry_dofs, dtype=np.int64), 2]
                    - float(z_plane)
                )
                <= tolerance
            )
        ]
        facets = np.asarray(selected_facets, dtype=np.int32)
    else:
        facets = np.unique(np.asarray(plane_facets, dtype=np.int32))

    msh.topology.create_connectivity(fdim, 1)
    facet_to_edge = msh.topology.connectivity(fdim, 1)
    if len(facets) == 0:
        edge_entities = np.empty(0, dtype=np.int32)
    else:
        edge_entities = np.unique(
            np.concatenate([facet_to_edge.links(int(facet)) for facet in facets])
        ).astype(np.int32)
    edge_map = _build_entity_dof_map(V, entity_dim=1, expected_entity_dofs=degree)
    face_map = _build_entity_dof_map(
        V, entity_dim=2, expected_entity_dofs=2 * degree * (degree - 1)
    )

    def traces(
        entities: np.ndarray,
        entity_dim: int,
        records: Mapping[int, Mapping[str, object]],
    ) -> tuple[EntityTrace, ...]:
        if len(entities) == 0:
            return ()
        geometry = cpp.mesh.entities_to_geometry(
            msh._cpp_object, entity_dim, entities, True
        )
        return tuple(
            EntityTrace(
                coordinates=np.asarray(
                    msh.geometry.x[np.asarray(geometry_dofs, dtype=np.int64)],
                    dtype=np.float64,
                ),
                original_dofs=np.asarray(
                    records[int(entity)]["global_dofs"], dtype=np.int64
                ),
            )
            for entity, geometry_dofs in zip(entities, geometry, strict=True)
        )

    edges = traces(edge_entities, 1, edge_map)
    faces = traces(facets, 2, face_map)
    if msh.comm.size > 1:
        def catalog(
            local_entities: tuple[EntityTrace, ...],
        ) -> tuple[EntityTrace, ...]:
            gathered = msh.comm.allgather(
                tuple(
                    (
                        canonical_entity_key(entity.coordinates, tolerance),
                        entity.coordinates,
                        entity.original_dofs,
                    )
                    for entity in local_entities
                )
            )
            by_key: dict[tuple[tuple[int, int, int], ...], EntityTrace] = {}
            for rank_entities in gathered:
                for key, coordinates, original_dofs in rank_entities:
                    candidate = EntityTrace(
                        coordinates=np.asarray(coordinates, dtype=np.float64),
                        original_dofs=np.asarray(original_dofs, dtype=np.int64),
                    )
                    previous = by_key.get(key)
                    if previous is not None:
                        if not np.allclose(
                            previous.coordinates,
                            candidate.coordinates,
                            atol=tolerance,
                            rtol=0.0,
                        ) or not np.array_equal(
                            previous.original_dofs,
                            candidate.original_dofs,
                        ):
                            raise AssertionError(
                                "MPI shared entity has inconsistent ordered "
                                "coordinates or global original DoFs"
                            )
                    else:
                        by_key[key] = candidate
            return tuple(by_key[key] for key in sorted(by_key))

        edges = catalog(edges)
        faces = catalog(faces)
    if len(edges) != 58 or len(faces) != 24:
        raise AssertionError(
            f"p5 6x4 endpoint entities {(len(edges), len(faces))} != (58, 24)"
        )
    return edges, faces


def _plane_snapshot(
    *,
    side: str,
    bottom_interface_z_nm: float,
    top_interface_z_nm: float,
    endpoint_z_nm: tuple[float, float],
    h_endpoint: str,
    tolerance: float,
    heartbeat: str,
) -> LivePlaneSnapshot:
    """Assemble one side system, copy its H-plane trace, then destroy it."""

    print(f"heartbeat: assembling {heartbeat}", flush=True)
    system = assemble_hybrid_local_dtn_system(
        _authority_config(),
        side,
        bottom_interface_z_nm=bottom_interface_z_nm,
        top_interface_z_nm=top_interface_z_nm,
        comm=MPI.COMM_WORLD,
        log=lambda message: print(
            f"heartbeat: {heartbeat}: {message}", flush=True
        ),
    )
    try:
        static = system.static_condensation
        if static is None:
            raise RuntimeError("assembly_time_static_condensed data is unavailable")
        first_facets = _facets_at_z(system.V, endpoint_z_nm[0], tolerance)
        second_facets = _facets_at_z(system.V, endpoint_z_nm[1], tolerance)
        endpoints = identify_endpoint_active_rows(
            system.V,
            static.condensed,
            left_facets=first_facets,
            right_facets=second_facets,
        )
        if h_endpoint == "left":
            original = endpoints.left_original.copy()
            active = endpoints.left_active.copy()
            h_facets = first_facets
        elif h_endpoint == "right":
            original = endpoints.right_original.copy()
            active = endpoints.right_active.copy()
            h_facets = second_facets
        else:
            raise ValueError("h_endpoint must be 'left' or 'right'")
        plane = build_trace_plane_view(static.condensed.trace_constraints, original, active)
        edges, faces = entity_traces_from_live_space(
            system.V,
            degree=5,
            plane_facets=h_facets,
            tolerance=tolerance,
        )
        snapshot = LivePlaneSnapshot(
            original_rows=original,
            active_rows=active,
            plane=plane,
            edges=edges,
            faces=faces,
        )
    finally:
        system.destroy()
        print(f"heartbeat: destroyed {heartbeat}", flush=True)
    return snapshot


def run_live_bottom_fixture() -> dict[str, object]:
    """Validate buffer-H to actual-endcap-H transfer without a forward solve."""

    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("--live-side bottom requires serial COMM_WORLD size=1")
    tolerance = 1.0e-8
    buffer_h = _plane_snapshot(
        side="bottom",
        bottom_interface_z_nm=40.0,
        top_interface_z_nm=80.0,
        endpoint_z_nm=(10.0, 40.0),
        h_endpoint="left",
        tolerance=tolerance,
        heartbeat="bottom buffer",
    )
    actual_h = _plane_snapshot(
        side="bottom",
        bottom_interface_z_nm=10.0,
        top_interface_z_nm=110.0,
        endpoint_z_nm=(-10.0, 10.0),
        h_endpoint="right",
        tolerance=tolerance,
        heartbeat="bottom actual endcap",
    )
    print("heartbeat: constructing and gating bottom H transfer", flush=True)
    build_bidirectional_transfers(
        buffer_h.edges,
        actual_h.edges,
        buffer_h.faces,
        actual_h.faces,
        buffer_h.plane,
        actual_h.plane,
        degree=5,
        z_shift=0.0,
        tolerance=tolerance,
    )
    return {
        "status": "pass",
        "live_side": "bottom",
        "buffer_h": {
            "original_rows": len(buffer_h.original_rows),
            "active_rows": len(buffer_h.active_rows),
            "edges": len(buffer_h.edges),
            "faces": len(buffer_h.faces),
        },
        "actual_endcap_h": {
            "original_rows": len(actual_h.original_rows),
            "active_rows": len(actual_h.active_rows),
            "edges": len(actual_h.edges),
            "faces": len(actual_h.faces),
        },
        "gates": {
            "counts": "pass",
            "constraint_identity_1250_rows": "pass",
            "bidirectional_roundtrip": "pass",
            "dual_pairing_forward_reverse": "pass",
        },
        "solve": "no_forward_solve",
    }


def run_live_top_fixture() -> dict[str, object]:
    """Validate top buffer-H to actual-endcap-H without a forward solve."""

    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("--live-side top requires serial COMM_WORLD size=1")
    tolerance = 1.0e-8
    buffer_h = _plane_snapshot(
        side="top",
        bottom_interface_z_nm=40.0,
        top_interface_z_nm=80.0,
        endpoint_z_nm=(80.0, 110.0),
        h_endpoint="right",
        tolerance=tolerance,
        heartbeat="top buffer",
    )
    actual_h = _plane_snapshot(
        side="top",
        bottom_interface_z_nm=10.0,
        top_interface_z_nm=110.0,
        endpoint_z_nm=(110.0, 130.0),
        h_endpoint="left",
        tolerance=tolerance,
        heartbeat="top actual endcap",
    )
    print("heartbeat: constructing and gating top H transfer", flush=True)
    build_bidirectional_transfers(
        buffer_h.edges,
        actual_h.edges,
        buffer_h.faces,
        actual_h.faces,
        buffer_h.plane,
        actual_h.plane,
        degree=5,
        z_shift=0.0,
        tolerance=tolerance,
    )
    return {
        "status": "pass",
        "live_side": "top",
        "buffer_h": {
            "original_rows": len(buffer_h.original_rows),
            "active_rows": len(buffer_h.active_rows),
            "edges": len(buffer_h.edges),
            "faces": len(buffer_h.faces),
        },
        "actual_endcap_h": {
            "original_rows": len(actual_h.original_rows),
            "active_rows": len(actual_h.active_rows),
            "edges": len(actual_h.edges),
            "faces": len(actual_h.faces),
        },
        "gates": {
            "counts": "pass",
            "constraint_identity_1250_rows": "pass",
            "bidirectional_roundtrip": "pass",
            "dual_pairing_forward_reverse": "pass",
        },
        "solve": "no_forward_solve",
    }


def _active_trace_columns(
    system: Any,
    h_active_rows: np.ndarray,
    modes: tuple[Any, ...],
) -> np.ndarray:
    """Interpolate analytic modes through the qualified active-port path."""

    columns: list[np.ndarray] = []
    for mode in modes:
        field = _interpolated_mode_field(
            system.V, mode.k_vector, mode.e_vector
        )
        system.floquet_data.mpc.homogenize(field)
        field.x.scatter_forward()
        columns.append(
            _active_values_for_port(
                field,
                system.static_condensation.condensed,
                h_active_rows,
            )
        )
    return np.column_stack(columns)


def _canonical_traction_columns(
    system: Any,
    h_active_rows: np.ndarray,
    modes: tuple[Any, ...],
    canonical_sign: complex,
) -> np.ndarray:
    """Reduce one analytic H-local traction vector per selected mode."""

    assemblers = tuple(
        _ReusableSurfaceComponentAssembler(
            system.V,
            system.local_mesh.mesh_data,
            system.local_mesh.interface_facet_tag,
            component,
            quadrature_degree=system.dtn_quadrature_degree,
        )
        for component in (0, 1)
    )
    columns: list[np.ndarray] = []
    for mode in modes:
        components = tuple(
            assembler.assemble_unconstrained_vector(mode)
            for assembler in assemblers
        )
        full_vector = components[0].copy()
        reduced = None
        try:
            local_traction = -np.asarray(
                _traction_vector(mode, system.cfg), dtype=np.complex128
            )
            full_vector.scale(PETSc.ScalarType(local_traction[0]))
            full_vector.axpy(PETSc.ScalarType(local_traction[1]), components[1])
            static = system.static_condensation
            if static is None:
                raise RuntimeError(
                    "Homogeneous Schur-q requires static condensation."
                )
            reduced = static.reduce_surface_vector(
                full_vector, role="load_column"
            )
            columns.append(
                complex(canonical_sign)
                * np.asarray(
                    reduced.getValues(
                        np.asarray(h_active_rows, dtype=PETSc.IntType)
                    ),
                    dtype=np.complex128,
                )
            )
        finally:
            if reduced is not None:
                reduced.destroy()
            full_vector.destroy()
            for vector in components:
                vector.destroy()
    return np.column_stack(columns)


def _gate_augmented_schur_columns(
    system: Any,
    action: Any,
    trace_columns: np.ndarray,
    numerical: np.ndarray,
    canonical_sign: complex,
) -> tuple[float, float]:
    """Check Schur columns against independent full augmented residuals."""

    q_error = 0.0
    complement_closure = 0.0
    trace = action.A_cH.createVecRight()
    complement_rhs = action.A_cH.createVecLeft()
    complement_solution = action.A_cc.createVecRight()
    complement_product = action.A_cc.createVecLeft()
    full = system.A.createVecRight()
    residual = system.A.createVecLeft()
    try:
        trace_first, trace_last = map(int, trace.getOwnershipRange())
        complement_ids = np.arange(action.complement_rows, dtype=PETSc.IntType)
        for column in range(trace_columns.shape[1]):
            trace.getArray()[:] = np.asarray(
                trace_columns[trace_first:trace_last, column],
                dtype=PETSc.ScalarType,
            )
            trace.assemble()
            action.A_cH.mult(trace, complement_rhs)
            action.factor.solve(complement_rhs, complement_solution)
            if int(action.factor.getConvergedReason()) < 0:
                raise RuntimeError(
                    "The independent augmented Schur extension did not converge."
                )
            complement_values = np.asarray(
                complement_solution.getValues(complement_ids),
                dtype=np.complex128,
            )
            action.A_cc.mult(complement_solution, complement_product)
            solve_scale = max(
                float(complement_rhs.norm()),
                float(complement_product.norm()),
                1.0e-30,
            )
            full.set(PETSc.ScalarType(0.0))
            full.setValues(
                action.retained_indices,
                np.asarray(trace_columns[:, column], dtype=PETSc.ScalarType),
            )
            full.setValues(
                action.complement_indices,
                np.asarray(-complement_values, dtype=PETSc.ScalarType),
            )
            full.assemble()
            system.A.mult(full, residual)
            q_full = complex(canonical_sign) * np.asarray(
                residual.getValues(action.retained_indices),
                dtype=np.complex128,
            )
            complement_residual = np.asarray(
                residual.getValues(action.complement_indices),
                dtype=np.complex128,
            )
            q_error = max(
                q_error,
                float(
                    np.linalg.norm(numerical[:, column] - q_full)
                    / max(
                        np.linalg.norm(numerical[:, column]),
                        np.linalg.norm(q_full),
                        1.0e-30,
                    )
                ),
            )
            complement_closure = max(
                complement_closure,
                float(np.linalg.norm(complement_residual) / solve_scale),
            )
    finally:
        for obj in (
            residual,
            full,
            complement_product,
            complement_solution,
            complement_rhs,
            trace,
        ):
            obj.destroy()
    if q_error > 1.0e-10 or complement_closure > 1.0e-10:
        raise AssertionError(
            "augmented Schur algebra gate failed: "
            f"q_error={q_error}, complement_closure={complement_closure}"
        )
    return q_error, complement_closure


def run_live_schur_q_fixture(side: str) -> dict[str, object]:
    """Run one homogeneous S/P physical-endcap Schur-q oracle fixture."""

    if side not in {"bottom", "top"}:
        raise ValueError("Schur-q side must be 'bottom' or 'top'.")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("Homogeneous Schur-q fixture requires serial execution.")
    authority = _authority_config()
    cfg = replace(
        authority,
        n_substrate=authority.n_air,
        n_grating=authority.n_air,
        substrate_material_label=None,
        grating_material_label=None,
    )
    endpoint_z = (-10.0, 10.0) if side == "bottom" else (110.0, 130.0)
    h_endpoint = "right" if side == "bottom" else "left"
    canonical_sign = 1.0 if side == "bottom" else -1.0
    print(f"heartbeat: assembling homogeneous {side} actual endcap", flush=True)
    system = assemble_hybrid_local_dtn_system(
        cfg,
        side,
        bottom_interface_z_nm=10.0,
        top_interface_z_nm=110.0,
        comm=MPI.COMM_WORLD,
        log=lambda message: print(
            f"heartbeat: homogeneous {side}: {message}", flush=True
        ),
    )
    action = None
    try:
        static = system.static_condensation
        if static is None:
            raise RuntimeError("assembly_time_static_condensed data is unavailable")
        first_facets = _facets_at_z(system.V, endpoint_z[0], 1.0e-8)
        second_facets = _facets_at_z(system.V, endpoint_z[1], 1.0e-8)
        endpoints = identify_endpoint_active_rows(
            system.V,
            static.condensed,
            left_facets=first_facets,
            right_facets=second_facets,
        )
        if h_endpoint == "right":
            h_active = endpoints.right_active
        else:
            h_active = endpoints.left_active
        modes = tuple(
            mode
            for mode in system.external_modes
            if mode.m == 0 and mode.n == 0 and mode.polarization in {"s", "p"}
        )
        if tuple(mode.polarization for mode in modes) != ("s", "p"):
            raise RuntimeError("The homogeneous fixture did not select zero-order S/P.")
        print(f"heartbeat: factoring homogeneous {side} complement", flush=True)
        action = build_hybrid_local_one_sided_schur_action(
            system, h_active, canonical_sign
        )
        trace_columns = _active_trace_columns(system, h_active, modes)
        oracle = _canonical_traction_columns(
            system, h_active, modes, canonical_sign
        )
        print(f"heartbeat: applying homogeneous {side} Schur-q", flush=True)
        numerical = action.apply_trace_columns(trace_columns)
        algebra_error, complement_closure = _gate_augmented_schur_columns(
            system,
            action,
            trace_columns,
            numerical,
            canonical_sign,
        )
        relative_errors = np.linalg.norm(numerical - oracle, axis=0) / np.linalg.norm(
            oracle, axis=0
        )
        result: dict[str, object] = {
            "status": "partial_pass_discrete_algebra_metric_not_run",
            "live_schur_q_side": side,
            "polarizations": [mode.polarization for mode in modes],
            "discrete_augmented_algebra": {
                "status": "pass",
                "action_vs_full_residual_relative": algebra_error,
                "complement_relative_closure": complement_closure,
                "relative_error_limit": 1.0e-10,
            },
            "continuum_interpolation_coefficient_norm_diagnostic": {
                "status": "measured_diagnostic_not_gate",
                "relative_errors": relative_errors.tolist(),
            },
            "official_q_metric": "not_run",
            "retained_rows": action.retained_rows,
            "complement_rows": action.complement_rows,
            "external_auxiliary_rows": action.external_auxiliary_rows,
            "full_coverage": bool(
                action.retained_rows + action.complement_rows == system.global_size
            ),
            "dense_interface_square_formed": action.dense_interface_square_formed,
            "solve": "no_forward_solve",
        }
        if side == "top":
            wrong_sign_errors = np.linalg.norm(-numerical - oracle, axis=0) / np.linalg.norm(
                oracle, axis=0
            )
            result["wrong_top_sign_relative_errors"] = wrong_sign_errors.tolist()
            result["wrong_top_sign_diagnostic_worse_than_correct"] = bool(
                np.all(wrong_sign_errors > relative_errors)
            )
        return result
    finally:
        if action is not None:
            action.destroy()
        system.destroy()
        print(f"heartbeat: destroyed homogeneous {side} endcap", flush=True)


def _gate_incoming_rhs_columns(
    system: Any,
    action: Any,
    augmented_rhs: np.ndarray,
    condensed_rhs: np.ndarray,
) -> tuple[float, float, np.ndarray]:
    """Check all incoming columns against the original augmented matrix."""

    max_h_error = 0.0
    max_complement_closure = 0.0
    reference_rhs = np.empty_like(condensed_rhs)
    complement_rhs = action.A_cc.createVecLeft()
    complement_solution = action.A_cc.createVecRight()
    complement_product = action.A_cc.createVecLeft()
    full = system.A.createVecRight()
    operator_action = system.A.createVecLeft()
    try:
        c_first, c_last = map(int, complement_rhs.getOwnershipRange())
        for column in range(augmented_rhs.shape[1]):
            complement_rhs.getArray()[:] = np.asarray(
                augmented_rhs[
                    action.complement_indices[c_first:c_last], column
                ],
                dtype=PETSc.ScalarType,
            )
            complement_rhs.assemble()
            action.factor.solve(complement_rhs, complement_solution)
            if int(action.factor.getConvergedReason()) < 0:
                raise RuntimeError("Incoming complement solve did not converge.")
            action.A_cc.mult(complement_solution, complement_product)
            complement_values = np.asarray(
                complement_solution.getValues(
                    np.arange(action.complement_rows, dtype=PETSc.IntType)
                ),
                dtype=np.complex128,
            )
            full.set(PETSc.ScalarType(0.0))
            full.setValues(action.complement_indices, complement_values)
            full.assemble()
            system.A.mult(full, operator_action)
            residual = augmented_rhs[:, column] - np.asarray(
                operator_action.getValues(
                    np.arange(system.global_size, dtype=PETSc.IntType)
                ),
                dtype=np.complex128,
            )
            canonical_h = action.canonical_sign * residual[
                action.retained_indices
            ]
            reference_rhs[:, column] = canonical_h
            max_h_error = max(
                max_h_error,
                float(
                    np.linalg.norm(
                        canonical_h - condensed_rhs[:, column]
                    )
                    / max(
                        np.linalg.norm(canonical_h),
                        np.linalg.norm(condensed_rhs[:, column]),
                        1.0e-30,
                    )
                ),
            )
            max_complement_closure = max(
                max_complement_closure,
                float(
                    np.linalg.norm(residual[action.complement_indices])
                    / max(
                        float(complement_rhs.norm()),
                        float(complement_product.norm()),
                        1.0e-30,
                    )
                ),
            )
    finally:
        for obj in (
            operator_action,
            full,
            complement_product,
            complement_solution,
            complement_rhs,
        ):
            obj.destroy()
    if max_h_error > 1.0e-10 or max_complement_closure > 1.0e-10:
        raise AssertionError(
            "incoming augmented RHS gate failed: "
            f"h_error={max_h_error}, "
            f"complement_closure={max_complement_closure}"
        )
    return max_h_error, max_complement_closure, reference_rhs


def run_live_incoming_fixture(side: str) -> dict[str, object]:
    """Run the actual-endcap incoming companion and direct-source Gate."""

    if side not in {"bottom", "top"}:
        raise ValueError("Incoming side must be 'bottom' or 'top'.")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("Incoming live fixture requires serial execution.")
    cfg = replace(_authority_config(), incident_amplitude=0.0j)
    print(f"heartbeat: assembling actual {side} incoming fixture", flush=True)
    system = assemble_hybrid_local_dtn_system(
        cfg,
        side,
        bottom_interface_z_nm=10.0,
        top_interface_z_nm=110.0,
        comm=MPI.COMM_WORLD,
        log=lambda message: print(
            f"heartbeat: incoming {side}: {message}", flush=True
        ),
    )
    action = None
    mass_actions: tuple[Any, ...] = ()
    try:
        static = system.static_condensation
        if static is None:
            raise RuntimeError("Incoming fixture requires static condensation.")
        endpoint_z = (-10.0, 10.0) if side == "bottom" else (110.0, 130.0)
        endpoints = identify_endpoint_active_rows(
            system.V,
            static.condensed,
            left_facets=_facets_at_z(system.V, endpoint_z[0], 1.0e-8),
            right_facets=_facets_at_z(system.V, endpoint_z[1], 1.0e-8),
        )
        h_active = (
            endpoints.right_active if side == "bottom" else endpoints.left_active
        )
        external_original = (
            endpoints.left_original if side == "bottom" else endpoints.right_original
        )
        external_active = (
            endpoints.left_active if side == "bottom" else endpoints.right_active
        )
        h_original = (
            endpoints.right_original if side == "bottom" else endpoints.left_original
        )
        canonical_sign = 1.0 if side == "bottom" else -1.0
        print(f"heartbeat: factoring actual {side} complement", flush=True)
        action = build_hybrid_local_one_sided_schur_action(
            system, h_active, canonical_sign
        )
        print(f"heartbeat: building sparse {side} endpoint mass actions", flush=True)
        mass_actions = build_endpoint_trace_mass_actions(
            system.V,
            system.local_mesh.mesh_data,
            static.condensed.trace_constraints,
            (
                EndpointTraceMassSelection(
                    system.local_mesh.external_facet_tag,
                    external_original,
                    external_active,
                ),
                EndpointTraceMassSelection(
                    system.local_mesh.interface_facet_tag,
                    h_original,
                    h_active,
                ),
            ),
        )
        external_mass, h_mass = mass_actions
        if not np.array_equal(external_mass.active_rows, external_active):
            raise AssertionError("External mass active-row order changed.")
        if not np.array_equal(h_mass.active_rows, h_active):
            raise AssertionError("H mass active-row order changed.")
        print(f"heartbeat: building 48 {side} incoming load columns", flush=True)
        loads = build_hybrid_local_incoming_load_columns(system)
        companions = loads.companions
        outgoing = system.external_modes
        if len(companions) != 48 or len(outgoing) != 48:
            raise AssertionError("Incoming companion count is not 48.")
        order_preserved = all(
            (
                incoming.side,
                incoming.m,
                incoming.n,
                incoming.polarization,
                incoming.beta,
                incoming.refractive_index,
            )
            == (
                out.side,
                out.m,
                out.n,
                out.polarization,
                out.beta,
                out.refractive_index,
            )
            for incoming, out in zip(companions, outgoing, strict=True)
        )
        if not order_preserved:
            raise AssertionError("Incoming companions changed outgoing order.")
        kz_reversal_error = max(
            abs(incoming.k_vector[2] + out.k_vector[2])
            for incoming, out in zip(companions, outgoing, strict=True)
        )
        transversality = max(
            abs(np.dot(mode.k_vector, mode.e_vector))
            / max(np.linalg.norm(mode.k_vector) * np.linalg.norm(mode.e_vector), 1.0e-30)
            for mode in companions
        )
        if kz_reversal_error > 1.0e-14 or transversality > 1.0e-12:
            raise AssertionError("Incoming Maxwell companion k/E Gate failed.")
        if loads.projection.shape != (48, 48) or not np.all(
            np.isfinite(loads.projection)
        ):
            raise AssertionError("Incoming projection is not finite 48x48.")
        off_order = max(
            (
                abs(loads.projection[row, column])
                for row, out in enumerate(outgoing)
                for column, incoming in enumerate(companions)
                if (out.m, out.n) != (incoming.m, incoming.n)
            ),
            default=0.0,
        )
        if off_order != 0.0:
            raise AssertionError("Incoming projection has nonzero cross-order entries.")
        if loads.augmented_rhs.shape != (system.global_size, 48):
            raise AssertionError("Incoming augmented RHS has the wrong shape.")
        auxiliary_max = float(
            np.max(np.abs(loads.augmented_rhs[system.n_fe :, :]), initial=0.0)
        )
        if auxiliary_max != 0.0:
            raise AssertionError("Incoming augmented RHS auxiliary rows are nonzero.")
        source_norm = float(system.b.norm())
        if source_norm != 0.0:
            raise AssertionError("incident_amplitude=0 left a constant system source.")
        direct_source = action.condense_rhs_columns(loads.augmented_rhs)
        h_error, complement_closure, reference_source = _gate_incoming_rhs_columns(
            system, action, loads.augmented_rhs, direct_source
        )
        difference_source = direct_source - reference_source
        difference_riesz = h_mass.solve_columns(difference_source)
        reference_riesz = h_mass.solve_columns(reference_source)
        action_riesz = h_mass.solve_columns(direct_source)
        q_metric_errors = np.sqrt(
            np.maximum(
                np.real(np.sum(difference_source.conj() * difference_riesz, axis=0)),
                0.0,
            )
        ) / np.maximum(
            np.maximum(
                np.sqrt(
                    np.maximum(
                        np.real(
                            np.sum(reference_source.conj() * reference_riesz, axis=0)
                        ),
                        0.0,
                    )
                ),
                np.sqrt(
                    np.maximum(
                        np.real(np.sum(direct_source.conj() * action_riesz, axis=0)),
                        0.0,
                    )
                ),
            ),
            1.0e-30,
        )
        official_q_error = float(np.max(q_metric_errors, initial=0.0))
        if official_q_error > 1.0e-10:
            raise AssertionError("Official H dual q metric exceeds 1e-10.")

        incoming_load = loads.augmented_rhs[external_active, :]
        incoming_riesz = external_mass.solve_columns(incoming_load)
        incoming_gram = (
            incoming_load.conj().T @ incoming_riesz
            / (1250.0 * float(system.cfg.k0) ** 2)
        )
        if incoming_gram.shape != (48, 48) or not np.all(
            np.isfinite(incoming_gram)
        ):
            raise AssertionError("Net incoming Gram is not finite 48x48.")
        gram_hermitian_relative = float(
            np.linalg.norm(incoming_gram - incoming_gram.conj().T)
            / max(np.linalg.norm(incoming_gram), 1.0e-30)
        )
        if gram_hermitian_relative > 1.0e-12:
            raise AssertionError("Net incoming Gram Hermitian defect exceeds 1e-12.")
        hermitian_gram = 0.5 * (incoming_gram + incoming_gram.conj().T)
        eigenvalues = np.linalg.eigvalsh(hermitian_gram)
        minimum_eigenvalue = float(eigenvalues[0])
        maximum_eigenvalue = float(eigenvalues[-1])
        gram_rank = int(np.count_nonzero(eigenvalues > 1.0e-10 * maximum_eigenvalue))
        if gram_rank != 48:
            raise AssertionError(f"Net incoming Gram rank is {gram_rank}, not 48.")
        raw_condition = float(maximum_eigenvalue / minimum_eigenvalue)
        gram_factor = np.linalg.cholesky(hermitian_gram)
        whitening = np.linalg.solve(
            gram_factor.conj().T, np.eye(48, dtype=np.complex128)
        )
        whitened_gram = whitening.conj().T @ hermitian_gram @ whitening
        whitening_error = float(
            np.linalg.norm(whitened_gram - np.eye(48), ord="fro")
            / np.sqrt(48.0)
        )
        if whitening_error > 1.0e-10:
            raise AssertionError("Net incoming Gram whitening exceeds 1e-10.")
        whitened_condition = float(np.linalg.cond(whitened_gram))
        direct_block = -direct_source
        amplitudes = np.arange(1, 49, dtype=np.complex128) + 1.0j * np.arange(
            48, 0, -1, dtype=np.complex128
        )
        direct_identity_error = float(
            np.linalg.norm(direct_block @ amplitudes + direct_source @ amplitudes)
            / max(np.linalg.norm(direct_source @ amplitudes), 1.0e-30)
        )
        if direct_identity_error > 1.0e-12:
            raise AssertionError("Direct traction block linear identity failed.")
        return {
            "status": f"partial_pass_q3a_{side}_metric_qualified",
            "live_incoming_side": side,
            "companions": 48,
            "companion_order_preserved": order_preserved,
            "maximum_kz_reversal_error": float(kz_reversal_error),
            "maximum_transversality_relative": float(transversality),
            "projection_shape": list(loads.projection.shape),
            "projection_cross_order_max_abs": float(off_order),
            "projection_finite": True,
            "augmented_rhs_shape": list(loads.augmented_rhs.shape),
            "augmented_rhs_auxiliary_max_abs": auxiliary_max,
            "system_zero_source_norm": source_norm,
            "retained_rows": action.retained_rows,
            "complement_rows": action.complement_rows,
            "external_auxiliary_rows": action.external_auxiliary_rows,
            "full_coverage": bool(
                action.retained_rows + action.complement_rows == system.global_size
            ),
            "dense_interface_square_formed": action.dense_interface_square_formed,
            "incoming_augmented_algebra": {
                "status": "pass",
                "condensed_vs_full_residual_relative": h_error,
                "complement_relative_closure": complement_closure,
                "relative_error_limit": 1.0e-10,
            },
            "endpoint_mass": {
                "external": {
                    "shape": list(external_mass.shape),
                    "hermitian_relative_defect": external_mass.hermitian_relative_defect,
                    "constraint_action_relative_error": external_mass.constraint_action_relative_error,
                    "solve_relative_residual": external_mass.solve_relative_residual,
                },
                "h": {
                    "shape": list(h_mass.shape),
                    "hermitian_relative_defect": h_mass.hermitian_relative_defect,
                    "constraint_action_relative_error": h_mass.constraint_action_relative_error,
                    "solve_relative_residual": h_mass.solve_relative_residual,
                },
            },
            "official_q_source_metric": {
                "status": "pass",
                "maximum_relative_dual_error": official_q_error,
                "relative_error_limit": 1.0e-10,
            },
            "incoming_gram_spd": {
                "status": "pass",
                "shape": [48, 48],
                "hermitian_relative_defect": gram_hermitian_relative,
                "rank_rcond_1e_10": gram_rank,
                "minimum_eigenvalue": minimum_eigenvalue,
                "maximum_eigenvalue": maximum_eigenvalue,
                "raw_condition": raw_condition,
            },
            "whitening": {
                "status": "pass",
                "identity_relative_frobenius": whitening_error,
                "relative_error_limit": 1.0e-10,
                "whitened_condition": whitened_condition,
            },
            "direct_block_definition": "-f_H_in",
            "direct_linear_identity_relative": direct_identity_error,
            "direct_linear_identity_limit": 1.0e-12,
            "cut_or_oversampled_transfer": "not_run",
            "full_weighted_adjoint": "not_run",
            "capacity": "not_run",
            "solve": "no_forward_solve",
        }
    finally:
        for mass_action in mass_actions:
            mass_action.destroy()
        if action is not None:
            action.destroy()
        system.destroy()
        print(f"heartbeat: destroyed actual {side} incoming fixture", flush=True)


def _full_augmented_residuals(
    system: Any, right_hand_sides: np.ndarray, states: np.ndarray
) -> np.ndarray:
    """Return explicit relative residuals from the original augmented matrix."""

    state = system.A.createVecRight()
    action = system.A.createVecLeft()
    residuals = np.empty(states.shape[1], dtype=np.float64)
    try:
        all_rows = np.arange(system.global_size, dtype=PETSc.IntType)
        for column in range(states.shape[1]):
            state.setValues(all_rows, states[:, column])
            state.assemble()
            system.A.mult(state, action)
            action_values = np.asarray(
                action.getValues(all_rows), dtype=np.complex128
            )
            residuals[column] = np.linalg.norm(
                action_values - right_hand_sides[:, column]
            ) / max(
                np.linalg.norm(action_values),
                np.linalg.norm(right_hand_sides[:, column]),
                1.0e-30,
            )
    finally:
        action.destroy()
        state.destroy()
    return residuals


def _full_augmented_hermitian_residuals(
    system: Any, right_hand_sides: np.ndarray, states: np.ndarray
) -> np.ndarray:
    """Return explicit ``A^H`` residuals from the original sparse matrix."""

    state = system.A.createVecLeft()
    action = system.A.createVecRight()
    residuals = np.empty(states.shape[1], dtype=np.float64)
    try:
        all_rows = np.arange(system.global_size, dtype=PETSc.IntType)
        for column in range(states.shape[1]):
            state.setValues(all_rows, states[:, column])
            state.assemble()
            system.A.multHermitian(state, action)
            action_values = np.asarray(
                action.getValues(all_rows), dtype=np.complex128
            )
            residuals[column] = np.linalg.norm(
                action_values - right_hand_sides[:, column]
            ) / max(
                np.linalg.norm(action_values),
                np.linalg.norm(right_hand_sides[:, column]),
                1.0e-30,
            )
    finally:
        action.destroy()
        state.destroy()
    return residuals


def run_live_buffer_transfer_fixture(
    side: str,
    *,
    weighted_adjoint: bool = False,
    core_snapshot: Mapping[str, Any] | None = None,
    randomized_capacity: bool = False,
) -> dict[str, object]:
    """Run three buffer harmonic-transfer columns without a forward solve."""

    if side not in {"bottom", "top"}:
        raise ValueError("Buffer transfer side must be 'bottom' or 'top'.")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("Buffer transfer fixture requires serial execution.")
    if randomized_capacity:
        weighted_adjoint = True
    if core_snapshot is not None and not weighted_adjoint:
        raise ValueError("A core snapshot requires the weighted-adjoint path.")
    if randomized_capacity and core_snapshot is None:
        raise ValueError("Q5 requires a qualified local-core snapshot.")
    cfg = replace(_authority_config(), incident_amplitude=0.0j)
    buffer = None
    actual = None
    actual_action = None
    buffer_solver = None
    sampler_ksp = None
    sampler_pc = None
    sampler_factor = None
    sampler_matrix = None
    q5_temporary = None
    mass_actions: tuple[Any, ...] = ()
    try:
        print(f"heartbeat: assembling {side} oversampled buffer", flush=True)
        buffer = assemble_hybrid_local_dtn_system(
            cfg,
            side,
            bottom_interface_z_nm=40.0,
            top_interface_z_nm=80.0,
            comm=MPI.COMM_WORLD,
            log=lambda message: print(
                f"heartbeat: {side} buffer: {message}", flush=True
            ),
        )
        print(f"heartbeat: assembling {side} actual endcap", flush=True)
        actual = assemble_hybrid_local_dtn_system(
            cfg,
            side,
            bottom_interface_z_nm=10.0,
            top_interface_z_nm=110.0,
            comm=MPI.COMM_WORLD,
            log=lambda message: print(
                f"heartbeat: {side} actual: {message}", flush=True
            ),
        )
        buffer_static = buffer.static_condensation
        actual_static = actual.static_condensation
        if buffer_static is None or actual_static is None:
            raise RuntimeError("Buffer transfer requires static condensation.")
        buffer_source_norm = float(buffer.b.norm())
        actual_source_norm = float(actual.b.norm())
        if buffer_source_norm != 0.0 or actual_source_norm != 0.0:
            raise AssertionError(
                "incident_amplitude=0 left a constant buffer or actual source."
            )

        cut_z, h_z, physical_z = (
            (40.0, 10.0, -10.0)
            if side == "bottom"
            else (80.0, 110.0, 130.0)
        )
        buffer_h_facets = _facets_at_z(buffer.V, h_z, 1.0e-8)
        cut_facets = _facets_at_z(buffer.V, cut_z, 1.0e-8)
        physical_facets = _facets_at_z(buffer.V, physical_z, 1.0e-8)
        first_view = identify_endpoint_active_rows(
            buffer.V,
            buffer_static.condensed,
            left_facets=(buffer_h_facets if side == "bottom" else cut_facets),
            right_facets=(cut_facets if side == "bottom" else buffer_h_facets),
        )
        second_view = identify_endpoint_active_rows(
            buffer.V,
            buffer_static.condensed,
            left_facets=(physical_facets if side == "bottom" else buffer_h_facets),
            right_facets=(buffer_h_facets if side == "bottom" else physical_facets),
        )
        first_h_active = (
            first_view.left_active if side == "bottom" else first_view.right_active
        )
        second_h_active = (
            second_view.right_active if side == "bottom" else second_view.left_active
        )
        if not np.array_equal(first_h_active, second_h_active):
            raise AssertionError("Buffer H active rows changed between endpoint views.")
        buffer_h_original = (
            first_view.left_original
            if side == "bottom"
            else first_view.right_original
        )
        buffer_h_active = first_h_active
        cut_active = (
            first_view.right_active if side == "bottom" else first_view.left_active
        )
        cut_original = (
            first_view.right_original
            if side == "bottom"
            else first_view.left_original
        )
        physical_active = (
            second_view.left_active
            if side == "bottom"
            else second_view.right_active
        )
        physical_original = (
            second_view.left_original
            if side == "bottom"
            else second_view.right_original
        )

        actual_physical_facets = _facets_at_z(actual.V, physical_z, 1.0e-8)
        actual_h_facets = _facets_at_z(actual.V, h_z, 1.0e-8)
        actual_endpoints = identify_endpoint_active_rows(
            actual.V,
            actual_static.condensed,
            left_facets=(
                actual_physical_facets if side == "bottom" else actual_h_facets
            ),
            right_facets=(
                actual_h_facets if side == "bottom" else actual_physical_facets
            ),
        )
        actual_h_original = (
            actual_endpoints.right_original
            if side == "bottom"
            else actual_endpoints.left_original
        )
        actual_h_active = (
            actual_endpoints.right_active
            if side == "bottom"
            else actual_endpoints.left_active
        )
        actual_physical_original = (
            actual_endpoints.left_original
            if side == "bottom"
            else actual_endpoints.right_original
        )
        actual_physical_active = (
            actual_endpoints.left_active
            if side == "bottom"
            else actual_endpoints.right_active
        )

        if weighted_adjoint:
            print("heartbeat: building Q3c sparse endpoint metrics", flush=True)
            buffer_metric_actions = build_endpoint_trace_mass_actions(
                buffer.V,
                buffer.local_mesh.mesh_data,
                buffer_static.condensed.trace_constraints,
                (
                    EndpointTraceMassSelection(
                        buffer.local_mesh.external_facet_tag,
                        physical_original,
                        physical_active,
                    ),
                    EndpointTraceMassSelection(
                        buffer.local_mesh.interface_facet_tag,
                        cut_original,
                        cut_active,
                    ),
                ),
            )
            actual_metric_actions = build_endpoint_trace_mass_actions(
                actual.V,
                actual.local_mesh.mesh_data,
                actual_static.condensed.trace_constraints,
                (
                    EndpointTraceMassSelection(
                        actual.local_mesh.external_facet_tag,
                        actual_physical_original,
                        actual_physical_active,
                    ),
                    EndpointTraceMassSelection(
                        actual.local_mesh.interface_facet_tag,
                        actual_h_original,
                        actual_h_active,
                    ),
                ),
            )
            mass_actions = (*buffer_metric_actions, *actual_metric_actions)
            if core_snapshot is not None:
                snapshot_rows = np.asarray(
                    core_snapshot["actual_h_active"], dtype=PETSc.IntType
                )
                if not np.array_equal(snapshot_rows, actual_h_active):
                    raise AssertionError(
                        f"Q4b {side} snapshot H-row order changed."
                    )

        buffer_h_plane = build_trace_plane_view(
            buffer_static.condensed.trace_constraints,
            buffer_h_original,
            buffer_h_active,
        )
        actual_h_plane = build_trace_plane_view(
            actual_static.condensed.trace_constraints,
            actual_h_original,
            actual_h_active,
        )
        buffer_h_edges, buffer_h_faces = entity_traces_from_live_space(
            buffer.V, degree=5, plane_facets=buffer_h_facets, tolerance=1.0e-8
        )
        actual_h_edges, actual_h_faces = entity_traces_from_live_space(
            actual.V, degree=5, plane_facets=actual_h_facets, tolerance=1.0e-8
        )
        print("heartbeat: constructing qualified buffer-H to actual-H mapper", flush=True)
        mapper, _reverse, _forward_blocks, _reverse_blocks = (
            build_bidirectional_transfers(
                buffer_h_edges,
                actual_h_edges,
                buffer_h_faces,
                actual_h_faces,
                buffer_h_plane,
                actual_h_plane,
                degree=5,
                z_shift=0.0,
                tolerance=1.0e-8,
            )
        )

        buffer_loads = build_hybrid_local_incoming_load_columns(buffer)
        actual_loads = build_hybrid_local_incoming_load_columns(actual)
        companion_coordinates_match = all(
            (
                buffer_mode.side,
                buffer_mode.m,
                buffer_mode.n,
                buffer_mode.polarization,
                buffer_mode.beta,
                buffer_mode.refractive_index,
            )
            == (
                actual_mode.side,
                actual_mode.m,
                actual_mode.n,
                actual_mode.polarization,
                actual_mode.beta,
                actual_mode.refractive_index,
            )
            for buffer_mode, actual_mode in zip(
                buffer_loads.companions,
                actual_loads.companions,
                strict=True,
            )
        )
        if not companion_coordinates_match:
            raise AssertionError(
                "Buffer and actual incoming companion coordinates differ."
            )
        if len(cut_active) != 1200 or len(buffer_loads.companions) != 48:
            raise AssertionError("Buffer logical source dimensions are not 1200+48.")
        overlap = np.intersect1d(cut_active, physical_active, assume_unique=True)
        if len(overlap):
            raise AssertionError("Cut and physical external active rows overlap.")
        incoming_cut_max = float(
            np.max(
                np.abs(buffer_loads.augmented_rhs[cut_active, :]), initial=0.0
            )
        )
        incoming_aux_max = float(
            np.max(
                np.abs(buffer_loads.augmented_rhs[buffer.n_fe :, :]), initial=0.0
            )
        )
        if incoming_cut_max != 0.0 or incoming_aux_max != 0.0:
            raise AssertionError("Buffer incoming RHS leaked to cut or auxiliary rows.")

        if randomized_capacity:
            buffer_external_mass, buffer_cut_mass, _, actual_h_mass = mass_actions
            alpha = 1.0 / 1250.0
            k0_squared = float(cfg.k0) ** 2
            incoming_load = buffer_loads.augmented_rhs[physical_active, :]
            raw_incoming_gram = incoming_load.conj().T @ (
                buffer_external_mass.solve_columns(incoming_load)
            )
            incoming_gram_defect = _relative_matrix_error(
                raw_incoming_gram, raw_incoming_gram.conj().T
            )
            incoming_gram = 0.5 * (
                raw_incoming_gram + raw_incoming_gram.conj().T
            )
            incoming_eigenvalues = np.linalg.eigvalsh(incoming_gram)
            incoming_rank = int(
                np.count_nonzero(
                    incoming_eigenvalues
                    > 1.0e-10 * incoming_eigenvalues[-1]
                )
            )
            if incoming_gram_defect > 1.0e-12 or incoming_rank != 48:
                raise AssertionError("Q5 incoming metric qualification failed.")

            sampler_matrix = _realify_hermitian_mass_sparse(
                buffer_cut_mass.matrix, incoming_gram
            )
            sampler_ksp = PETSc.KSP().create(PETSc.COMM_SELF)
            sampler_ksp.setOperators(sampler_matrix)
            sampler_ksp.setType(PETSc.KSP.Type.PREONLY)
            sampler_pc = sampler_ksp.getPC()
            sampler_pc.setType(PETSc.PC.Type.CHOLESKY)
            sampler_pc.setFactorSolverType("petsc")
            sampler_ksp.setUp()
            sampler_factor = sampler_pc.getFactorMatrix()
            sampler_matrix_type = sampler_matrix.getType()
            sampler_factor_solver = sampler_pc.getFactorSolverType()
            sampler_factor_type = sampler_factor.getType()
            sampler_shape = sampler_matrix.getSize()
            sampler_nnz = int(
                sampler_matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)["nz_used"]
            )
            expected_nnz_bound = 4 * (
                int(
                    buffer_cut_mass.matrix.getInfo(
                        PETSc.Mat.InfoType.GLOBAL_SUM
                    )["nz_used"]
                )
                + int(np.count_nonzero(incoming_gram))
            )
            if (
                sampler_matrix_type != "seqsbaij"
                or sampler_factor_solver != "petsc"
                or sampler_shape != (2496, 2496)
                or sampler_nnz > expected_nnz_bound
            ):
                raise AssertionError("Q5 realified sampler sparse shape/nnz failed.")
            sampler_transpose = PETSc.Mat()
            sampler_matrix.transpose(sampler_transpose)
            sampler_difference = sampler_matrix.copy()
            try:
                sampler_difference.axpy(-1.0, sampler_transpose)
                sampler_symmetry_defect = float(
                    sampler_difference.norm()
                    / max(sampler_matrix.norm(), 1.0e-30)
                )
            finally:
                sampler_difference.destroy()
                sampler_transpose.destroy()
            sampler_probe = np.arange(1, 1249, dtype=np.complex128) * (
                1.0 - 0.25j
            )
            sampler_probe /= np.linalg.norm(sampler_probe)
            real_probe = sampler_matrix.createVecRight()
            real_action = sampler_matrix.createVecLeft()
            try:
                real_probe.getArray()[:] = np.concatenate(
                    (sampler_probe.real, sampler_probe.imag)
                )
                real_probe.assemble()
                sampler_matrix.mult(real_probe, real_action)
                action_values = real_action.getArray(readonly=True)
                complex_action = action_values[:1248] + 1.0j * action_values[1248:]
                expected_action = np.concatenate(
                    (
                        buffer_cut_mass.multiply_columns(
                            sampler_probe[:1200]
                        )[:, 0],
                        incoming_gram @ sampler_probe[1200:],
                    )
                )
                sampler_action_error = _relative_matrix_error(
                    complex_action, expected_action
                )
                sampler_quadratic_error = float(
                    abs(
                        np.vdot(sampler_probe, expected_action)
                        - real_probe.dot(real_action)
                    )
                    / max(abs(np.vdot(sampler_probe, expected_action)), 1.0e-30)
                )
            finally:
                real_action.destroy()
                real_probe.destroy()

            seed_children = np.random.SeedSequence(36061).spawn(4)
            seed_offset = 0 if side == "bottom" else 2
            range_rng = np.random.Generator(
                np.random.PCG64(seed_children[seed_offset])
            )
            holdout_rng = np.random.Generator(
                np.random.PCG64(seed_children[seed_offset + 1])
            )
            q5_temporary = tempfile.TemporaryDirectory(
                prefix=f"task036_q5_{side}_"
            )
            range_sources = np.memmap(
                f"{q5_temporary.name}/range_sources.dat",
                mode="w+",
                dtype=np.complex128,
                shape=(1248, 256),
            )
            holdout_sources = np.memmap(
                f"{q5_temporary.name}/holdout_sources.dat",
                mode="w+",
                dtype=np.complex128,
                shape=(1248, 20),
            )
            sampler_identity_errors: list[float] = []
            sampler_half_residuals: list[float] = []
            sampler_imaginary_leakages: list[float] = []
            sample_scale = float(cfg.k0) / np.sqrt(alpha)
            for destination, rng in (
                (range_sources, range_rng),
                (holdout_sources, holdout_rng),
            ):
                for start in range(0, destination.shape[1], 16):
                    stop = min(start + 16, destination.shape[1])
                    sampled, gaussian, half_residual, imaginary_leakage = (
                        _sample_q5_metric_isotropic_sources(
                            rng,
                            stop - start,
                            sampler_factor,
                            sampler_matrix,
                            buffer_cut_mass,
                            scale=sample_scale,
                        )
                    )
                    destination[:, start:stop] = sampled
                    gs_sampled = np.vstack(
                        (
                            alpha
                            / k0_squared
                            * buffer_cut_mass.solve_columns(sampled[:1200]),
                            alpha
                            / k0_squared
                            * incoming_gram @ sampled[1200:],
                        )
                    )
                    sampler_identity_errors.append(
                        _relative_matrix_error(
                            np.real(sampled.conj().T @ gs_sampled),
                            np.real(gaussian.conj().T @ gaussian),
                        )
                    )
                    sampler_half_residuals.append(half_residual)
                    sampler_imaginary_leakages.append(imaginary_leakage)
            if sampler_action_error > 1.0e-12:
                raise AssertionError("Q5 sampler realification action failed.")
            if sampler_quadratic_error > 1.0e-12:
                raise AssertionError("Q5 sampler quadratic identity failed.")
            if max(sampler_half_residuals) > 1.0e-11:
                raise AssertionError("Q5 sampler forward/backward residual failed.")
            if max(sampler_identity_errors) > 1.0e-10:
                raise AssertionError("Q5 sampler block Gram identity failed.")
            if sampler_symmetry_defect > 1.0e-13:
                raise AssertionError("Q5 sampler transpose symmetry failed.")
            if max(sampler_imaginary_leakages) > 1.0e-13:
                raise AssertionError("Q5 sampler imaginary leakage failed.")
            sampler_factor.destroy()
            sampler_factor = None
            sampler_pc.destroy()
            sampler_pc = None
            sampler_ksp.destroy()
            sampler_ksp = None
            sampler_matrix.destroy()
            sampler_matrix = None

            output_range = np.memmap(
                f"{q5_temporary.name}/range_output.dat",
                mode="w+",
                dtype=np.complex128,
                shape=(2400, 256),
            )
            output_holdout = np.memmap(
                f"{q5_temporary.name}/holdout_output.dat",
                mode="w+",
                dtype=np.complex128,
                shape=(2400, 20),
            )
            buffer_states = np.memmap(
                f"{q5_temporary.name}/buffer_h_states.dat",
                mode="w+",
                dtype=np.complex128,
                shape=(1200, 276),
            )
            primal_residual_max = 0.0
            print(f"heartbeat: Q5 factoring {side} buffer #1", flush=True)
            buffer_solver = build_hybrid_local_full_matrix_solve_action(buffer)
            for destination, offset, sources in (
                (output_range, 0, range_sources),
                (output_holdout, 256, holdout_sources),
            ):
                for start in range(0, sources.shape[1], 16):
                    stop = min(start + 16, sources.shape[1])
                    source_block = np.asarray(sources[:, start:stop])
                    rhs = np.zeros(
                        (buffer.global_size, stop - start), dtype=np.complex128
                    )
                    rhs[cut_active] = source_block[:1200]
                    rhs += buffer_loads.augmented_rhs @ source_block[1200:]
                    states = buffer_solver.solve_columns(rhs)
                    primal_residual_max = max(
                        primal_residual_max,
                        float(np.max(_full_augmented_residuals(buffer, rhs, states))),
                    )
                    buffer_states[:, offset + start : offset + stop] = states[
                        buffer_h_active
                    ]
            if primal_residual_max > 1.0e-10:
                raise AssertionError("Q5 primal residual exceeds 1e-10.")
            buffer_solver.destroy()
            buffer_solver = None

            def gc_action(values: np.ndarray) -> np.ndarray:
                return _joint_cauchy_metric_action(
                    actual_h_mass, values, alpha=alpha, k0=cfg.k0
                )

            white_core = np.asarray(core_snapshot["white_core"])

            def cperp(values: np.ndarray) -> np.ndarray:
                return values - white_core @ (
                    white_core.conj().T @ gc_action(values)
                )

            print(f"heartbeat: Q5 factoring {side} actual Schur", flush=True)
            actual_action = build_hybrid_local_one_sided_schur_action(
                actual, actual_h_active, 1.0 if side == "bottom" else -1.0
            )
            actual_direct_source = actual_action.condense_rhs_columns(
                actual_loads.augmented_rhs
            )
            for destination, offset, sources in (
                (output_range, 0, range_sources),
                (output_holdout, 256, holdout_sources),
            ):
                for start in range(0, sources.shape[1], 16):
                    stop = min(start + 16, sources.shape[1])
                    source_block = np.asarray(sources[:, start:stop])
                    electric_block = np.column_stack(
                        [
                            mapper.primal(buffer_states[:, offset + column])
                            for column in range(start, stop)
                        ]
                    )
                    traction_block = actual_action.apply_trace_columns(
                        electric_block
                    ) - actual_direct_source @ source_block[1200:]
                    destination[:, start:stop] = cperp(
                        np.vstack((electric_block, traction_block))
                    )

            q_basis = np.memmap(
                f"{q5_temporary.name}/q_basis.dat",
                mode="w+",
                dtype=np.complex128,
                shape=(2400, 256),
            )
            effective_rank = 0
            for start in range(0, 256, 16):
                block = _gc_projected_orthonormalize_block(
                    np.asarray(output_range[:, start : start + 16]),
                    q_basis[:, :effective_rank],
                    gc_action,
                    cperp,
                )
                accepted = min(block.shape[1], 256 - effective_rank)
                q_basis[:, effective_rank : effective_rank + accepted] = block[
                    :, :accepted
                ]
                effective_rank += accepted
                if effective_rank == 256:
                    break
            q_gram = np.zeros((effective_rank, effective_rank), dtype=np.complex128)
            for start in range(0, effective_rank, 16):
                stop = min(start + 16, effective_rank)
                metric_block = gc_action(np.asarray(q_basis[:, start:stop]))
                for row_start in range(0, effective_rank, 16):
                    row_stop = min(row_start + 16, effective_rank)
                    q_gram[row_start:row_stop, start:stop] = (
                        np.asarray(q_basis[:, row_start:row_stop]).conj().T
                        @ metric_block
                    )
            q_orthogonality = _relative_matrix_error(
                q_gram, np.eye(effective_rank)
            )
            if q_orthogonality > 1.0e-10:
                raise AssertionError("Q5 range basis G_C orthogonality failed.")

            source_range_gram = np.empty((256, 256), dtype=np.complex128)
            output_range_gram = np.empty((256, 256), dtype=np.complex128)
            for start in range(0, 256, 16):
                stop = start + 16
                source_block = np.asarray(range_sources[:, start:stop])
                source_metric_block = np.vstack(
                    (
                        alpha
                        / k0_squared
                        * buffer_cut_mass.solve_columns(source_block[:1200]),
                        alpha
                        / k0_squared
                        * incoming_gram @ source_block[1200:],
                    )
                )
                output_block = np.asarray(output_range[:, start:stop])
                output_metric_block = gc_action(output_block)
                for row_start in range(0, 256, 16):
                    row_stop = row_start + 16
                    source_range_gram[row_start:row_stop, start:stop] = (
                        np.asarray(
                            range_sources[:, row_start:row_stop]
                        ).conj().T
                        @ source_metric_block
                    )
                    output_range_gram[row_start:row_stop, start:stop] = (
                        np.asarray(
                            output_range[:, row_start:row_stop]
                        ).conj().T
                        @ output_metric_block
                    )
            source_range_gram_defect = _relative_matrix_error(
                source_range_gram, source_range_gram.conj().T
            )
            output_range_gram_defect = _relative_matrix_error(
                output_range_gram, output_range_gram.conj().T
            )
            source_range_gram = 0.5 * (
                source_range_gram + source_range_gram.conj().T
            )
            output_range_gram = 0.5 * (
                output_range_gram + output_range_gram.conj().T
            )
            primal_lower_valid = True
            try:
                source_range_factor = np.linalg.cholesky(source_range_gram)
                reduced_range = np.linalg.solve(
                    source_range_factor, output_range_gram
                )
                reduced_range = np.linalg.solve(
                    source_range_factor.conj(), reduced_range.T
                ).T
                generalized_eigenvalues, generalized_vectors = np.linalg.eigh(
                    0.5 * (reduced_range + reduced_range.conj().T)
                )
                sigma1_primal_small_estimate = float(
                    np.sqrt(max(generalized_eigenvalues[-1], 0.0))
                )
                generalized_direction = np.linalg.solve(
                    source_range_factor.conj().T,
                    generalized_vectors[:, -1],
                )
                source_direction = np.zeros(1248, dtype=np.complex128)
                output_direction = np.zeros(2400, dtype=np.complex128)
                for start in range(0, 256, 16):
                    stop = start + 16
                    source_direction += np.asarray(
                        range_sources[:, start:stop]
                    ) @ generalized_direction[start:stop]
                    output_direction += np.asarray(
                        output_range[:, start:stop]
                    ) @ generalized_direction[start:stop]
                source_direction_metric = np.concatenate(
                    (
                        alpha
                        / k0_squared
                        * buffer_cut_mass.solve_columns(
                            source_direction[:1200]
                        )[:, 0],
                        alpha
                        / k0_squared
                        * incoming_gram @ source_direction[1200:],
                    )
                )
                output_direction_metric = gc_action(output_direction)[:, 0]
                sigma1_primal_lower = float(
                    np.sqrt(
                        max(
                            float(
                                np.real(
                                    np.vdot(
                                        output_direction,
                                        output_direction_metric,
                                    )
                                    / np.vdot(
                                        source_direction,
                                        source_direction_metric,
                                    )
                                )
                            ),
                            0.0,
                        )
                    )
                )
                primal_lower_small_explicit_relative_difference = float(
                    abs(sigma1_primal_small_estimate - sigma1_primal_lower)
                    / max(
                        sigma1_primal_small_estimate,
                        sigma1_primal_lower,
                        1.0e-30,
                    )
                )
                primal_lower_valid = bool(
                    np.isfinite(sigma1_primal_lower)
                    and sigma1_primal_lower > 0.0
                )
            except np.linalg.LinAlgError:
                sigma1_primal_small_estimate = 0.0
                sigma1_primal_lower = 0.0
                primal_lower_small_explicit_relative_difference = np.inf
                primal_lower_valid = False

            adjoint_rhs = np.memmap(
                f"{q5_temporary.name}/adjoint_rhs.dat",
                mode="w+",
                dtype=np.complex128,
                shape=(buffer.global_size, effective_rank),
            )
            direct_adjoint = np.memmap(
                f"{q5_temporary.name}/direct_adjoint.dat",
                mode="w+",
                dtype=np.complex128,
                shape=(48, effective_rank),
            )
            complement_reprojection_numerator = 0.0
            complement_reprojection_denominator = 0.0
            for start in range(0, effective_rank, 16):
                stop = min(start + 16, effective_rank)
                q_block = np.asarray(q_basis[:, start:stop])
                projected_q_block = cperp(q_block)
                difference = projected_q_block - q_block
                complement_reprojection_numerator += float(
                    np.sum(
                        np.real(
                            difference.conj() * gc_action(difference)
                        )
                    )
                )
                complement_reprojection_denominator += float(
                    np.sum(np.real(q_block.conj() * gc_action(q_block)))
                )
                weighted = gc_action(projected_q_block)
                weighted_e, weighted_q = np.split(weighted, 2, axis=0)
                u_h = weighted_e + actual_action.apply_trace_hermitian_columns(
                    weighted_q
                )
                adjoint_rhs[:, start:stop] = 0.0
                for column in range(stop - start):
                    adjoint_rhs[buffer_h_active, start + column] = mapper.dual(
                        u_h[:, column]
                    )
                direct_adjoint[:, start:stop] = (
                    -actual_direct_source
                ).conj().T @ weighted_q
            complement_reprojection_error = float(
                np.sqrt(
                    max(complement_reprojection_numerator, 0.0)
                    / max(complement_reprojection_denominator, 1.0e-30)
                )
            )
            if complement_reprojection_error > 1.0e-10:
                print(
                    "heartbeat: Q5 complement reprojection error "
                    f"{complement_reprojection_error:.17e}",
                    flush=True,
                )
                raise AssertionError(
                    "Q5 complement reprojection failed: "
                    f"{complement_reprojection_error:.17e}"
                )
            actual_action.destroy()
            actual_action = None

            projected_adjoint = np.memmap(
                f"{q5_temporary.name}/projected_adjoint.dat",
                mode="w+",
                dtype=np.complex128,
                shape=(1248, effective_rank),
            )
            adjoint_residual_max = 0.0
            incoming_factor = np.linalg.cholesky(incoming_gram)
            print(f"heartbeat: Q5 factoring {side} buffer #2", flush=True)
            buffer_solver = build_hybrid_local_full_matrix_solve_action(buffer)
            for start in range(0, effective_rank, 16):
                stop = min(start + 16, effective_rank)
                rhs = np.asarray(adjoint_rhs[:, start:stop])
                states = buffer_solver.solve_hermitian_columns(rhs)
                adjoint_residual_max = max(
                    adjoint_residual_max,
                    float(
                        np.max(
                            _full_augmented_hermitian_residuals(
                                buffer, rhs, states
                            )
                        )
                    ),
                )
                raw_cut = states[cut_active]
                raw_in = (
                    buffer_loads.augmented_rhs.conj().T @ states
                    + direct_adjoint[:, start:stop]
                )
                projected_adjoint[:1200, start:stop] = (
                    k0_squared
                    / alpha
                    * buffer_cut_mass.multiply_columns(raw_cut)
                )
                incoming_first = np.linalg.solve(incoming_factor, raw_in)
                projected_adjoint[1200:, start:stop] = (
                    k0_squared
                    / alpha
                    * np.linalg.solve(
                        incoming_factor.conj().T, incoming_first
                    )
                )
            if adjoint_residual_max > 1.0e-9:
                raise AssertionError("Q5 adjoint residual exceeds 1e-9.")
            buffer_solver.destroy()
            buffer_solver = None

            small_h = np.empty(
                (effective_rank, effective_rank), dtype=np.complex128
            )
            for start in range(0, effective_rank, 16):
                stop = min(start + 16, effective_rank)
                projected_block = np.asarray(
                    projected_adjoint[:, start:stop]
                )
                metric_block = np.vstack(
                    (
                        alpha
                        / k0_squared
                        * buffer_cut_mass.solve_columns(
                            projected_block[:1200]
                        ),
                        alpha
                        / k0_squared
                        * incoming_gram @ projected_block[1200:],
                    )
                )
                for row_start in range(0, effective_rank, 16):
                    row_stop = min(row_start + 16, effective_rank)
                    small_h[row_start:row_stop, start:stop] = (
                        np.asarray(
                            projected_adjoint[:, row_start:row_stop]
                        ).conj().T
                        @ metric_block
                    )
            small_eigenvalues, small_vectors = np.linalg.eigh(
                0.5 * (small_h + small_h.conj().T)
            )
            order = np.argsort(small_eigenvalues)[::-1]
            ritz_sigma = np.sqrt(np.maximum(small_eigenvalues[order], 0.0))
            small_vectors = small_vectors[:, order]
            tail_summary = singular_tail_summary(ritz_sigma)
            holdout_multiplier = complex_gaussian_holdout_multiplier(
                1.0e-12 / 482.0, 20
            )
            holdout_metric = np.empty_like(output_holdout)
            for start in range(0, 20, 16):
                stop = min(start + 16, 20)
                holdout_metric[:, start:stop] = gc_action(
                    np.asarray(output_holdout[:, start:stop])
                )
            q_coordinates = np.empty((effective_rank, 20), dtype=np.complex128)
            for start in range(0, effective_rank, 16):
                stop = min(start + 16, effective_rank)
                q_coordinates[start:stop] = (
                    np.asarray(q_basis[:, start:stop]).conj().T @ holdout_metric
                )
            u_coordinates = small_vectors.conj().T @ q_coordinates
            certified_tail = np.full(241, np.inf, dtype=np.float64)
            holdout_residual = np.asarray(output_holdout).copy()
            holdout_valid = bool(
                primal_lower_valid
            )
            for rank in range(241):
                residual_quadratic = np.empty(20, dtype=np.float64)
                for start in range(0, 20, 16):
                    stop = min(start + 16, 20)
                    residual_block = holdout_residual[:, start:stop]
                    residual_quadratic[start:stop] = np.sum(
                        np.real(
                            residual_block.conj() * gc_action(residual_block)
                        ),
                        axis=0,
                    )
                negative_limit = -1.0e-12 * max(
                    float(np.max(np.abs(residual_quadratic))), 1.0e-30
                )
                if (
                    not np.all(np.isfinite(residual_quadratic))
                    or np.min(residual_quadratic) < negative_limit
                    or not holdout_valid
                ):
                    holdout_valid = False
                    break
                residual = np.sqrt(np.maximum(residual_quadratic, 0.0))
                certified_tail[rank] = (
                    holdout_multiplier
                    * np.max(residual)
                    / sigma1_primal_lower
                )
                if rank < min(240, effective_rank):
                    ritz_vector = np.zeros(2400, dtype=np.complex128)
                    for start in range(0, effective_rank, 16):
                        stop = min(start + 16, effective_rank)
                        ritz_vector += np.asarray(
                            q_basis[:, start:stop]
                        ) @ small_vectors[start:stop, rank]
                    for start in range(0, 20, 16):
                        stop = min(start + 16, 20)
                        holdout_residual[:, start:stop] -= (
                            ritz_vector[:, None]
                            * u_coordinates[rank, start:stop][None, :]
                        )
            certified_ranks: dict[str, int | str] = {}
            for threshold in (1.0e-6, 1.0e-8, 1.0e-10):
                reached = np.flatnonzero(certified_tail <= threshold)
                certified_ranks[str(threshold)] = (
                    int(reached[0]) if len(reached) else "not_reached"
                )
            if not holdout_valid:
                certified_ranks = {
                    str(threshold): "not_reached"
                    for threshold in (1.0e-6, 1.0e-8, 1.0e-10)
                }
            reached_1e_8 = (
                holdout_valid
                and certified_ranks[str(1.0e-8)] != "not_reached"
            )
            return {
                "status": (
                    f"partial_pass_q5_{side}_randomized_capacity"
                    if reached_1e_8
                    else f"controlled_stop_q5_{side}_tail_1e_8_not_reached"
                ),
                "side": side,
                "constants": {
                    "base_seed": 36061,
                    "block": 16,
                    "r_cap": 240,
                    "oversampling": 16,
                    "sketch_width": 256,
                    "holdout": 20,
                    "power_iterations": 0,
                    "events": 482,
                    "delta_each": 1.0e-12 / 482.0,
                    "holdout_multiplier": holdout_multiplier,
                },
                "sampler": {
                    "realified_shape": sampler_shape,
                    "realified_nnz": sampler_nnz,
                    "nnz_bound": expected_nnz_bound,
                    "matrix_type": sampler_matrix_type,
                    "factor_type": sampler_factor_type,
                    "factor_solver": sampler_factor_solver,
                    "half_action": "solveBackward",
                    "realification_action_relative_error": sampler_action_error,
                    "realification_quadratic_relative_error": (
                        sampler_quadratic_error
                    ),
                    "realification_transpose_symmetry_relative_error": (
                        sampler_symmetry_defect
                    ),
                    "forward_backward_relative_residual": max(
                        sampler_half_residuals
                    ),
                    "half_solve_output_imaginary_leakage": max(
                        sampler_imaginary_leakages
                    ),
                    "block_real_gram_half_isometry_max_relative_error": max(
                        sampler_identity_errors
                    ),
                    "maximum_simultaneous_metric_factors": 5,
                    "sampler_destroyed_before_large_factor": True,
                },
                "effective_rank": effective_rank,
                "ritz_sigma": ritz_sigma.tolist(),
                "gc_orthogonality_relative_error": q_orthogonality,
                "ritz_tail_summary": {
                    key: (
                        value.tolist() if isinstance(value, np.ndarray) else value
                    )
                    for key, value in tail_summary.items()
                },
                "certified_relative_tail": certified_tail.tolist(),
                "certified_ranks": certified_ranks,
                "holdout_residual_method": "direct_projected_vector_norm",
                "resident_holdout_shape": [2400, 20],
                "certificate_denominator": (
                    "primal_range_generalized_rayleigh_lower_bound"
                ),
                "sigma1_primal_lower": sigma1_primal_lower,
                "sigma1_primal_small_generalized_eig_estimate": (
                    sigma1_primal_small_estimate
                ),
                "sigma1_primal_small_explicit_relative_difference": (
                    primal_lower_small_explicit_relative_difference
                ),
                "source_range_gram_hermitian_relative_defect": (
                    source_range_gram_defect
                ),
                "output_range_gram_hermitian_relative_defect": (
                    output_range_gram_defect
                ),
                "ritz_sigma1_role": "adjoint_ritz_diagnostic",
                "probabilistic_scope": "numerically_applied_transfer",
                "global_failure_probability": 1.0e-12,
                "holdout_direct_quadratic_valid": holdout_valid,
                "primal_range_denominator_valid": primal_lower_valid,
                "complement_reprojection_relative_error": (
                    complement_reprojection_error
                ),
                "primal_residual_max": primal_residual_max,
                "adjoint_residual_max": adjoint_residual_max,
                "direct_included": True,
                "buffer_factorizations": 2,
                "actual_schur_factorizations": 1,
                "maximum_simultaneous_local_large_factors": 1,
                "dense_full_transfer_formed": False,
                "capacity_tail": "measured_randomized_certificate",
                "forward_pde": "not_run",
            }

        eta_cut = np.arange(1, 1201, dtype=np.complex128) + 1.0j * np.arange(
            1200, 0, -1, dtype=np.complex128
        )
        eta_cut /= np.linalg.norm(eta_cut)
        incoming_amplitude = np.arange(1, 49, dtype=np.complex128) + 1.0j * np.arange(
            48, 0, -1, dtype=np.complex128
        )
        incoming_amplitude /= np.linalg.norm(incoming_amplitude)
        cut_rhs = np.zeros(buffer.global_size, dtype=np.complex128)
        cut_rhs[cut_active] = eta_cut
        incoming_rhs = buffer_loads.augmented_rhs @ incoming_amplitude
        right_hand_sides = np.column_stack(
            (cut_rhs, incoming_rhs, cut_rhs + incoming_rhs)
        )
        weighted_record: dict[str, object] | str = "not_run"
        adjoint_rhs = None
        direct_adjoint = None
        if weighted_adjoint:
            buffer_external_mass, buffer_cut_mass, _actual_external_mass, actual_h_mass = (
                mass_actions
            )
            alpha = 1.0 / 1250.0
            k0_squared = float(cfg.k0) ** 2
            incoming_load = buffer_loads.augmented_rhs[physical_active, :]
            raw_incoming_gram = incoming_load.conj().T @ (
                buffer_external_mass.solve_columns(incoming_load)
            )
            incoming_gram_hermitian_defect = float(
                np.linalg.norm(raw_incoming_gram - raw_incoming_gram.conj().T)
                / max(np.linalg.norm(raw_incoming_gram), 1.0e-30)
            )
            if incoming_gram_hermitian_defect > 1.0e-12:
                raise AssertionError("Q3c incoming Gram Hermitian defect exceeds 1e-12.")
            incoming_gram = 0.5 * (
                raw_incoming_gram + raw_incoming_gram.conj().T
            )
            incoming_eigenvalues = np.linalg.eigvalsh(incoming_gram)
            incoming_rank = int(
                np.count_nonzero(
                    incoming_eigenvalues
                    > 1.0e-10 * float(incoming_eigenvalues[-1])
                )
            )
            if incoming_rank != 48:
                raise AssertionError("Q3c incoming Gram rank is not 48.")
            incoming_factor = np.linalg.cholesky(incoming_gram)
            e_probe = np.arange(1, 1201, dtype=np.complex128) + 1.0j * np.arange(
                3, 1203, dtype=np.complex128
            )
            e_probe /= np.linalg.norm(e_probe)
            q_probe = np.arange(1200, 0, -1, dtype=np.complex128) + 1.0j * np.arange(
                7, 1207, dtype=np.complex128
            )
            q_probe /= np.linalg.norm(q_probe)
            test_electric = np.column_stack(
                (e_probe, np.zeros(1200, dtype=np.complex128), e_probe)
            )
            test_traction = np.column_stack(
                (np.zeros(1200, dtype=np.complex128), q_probe, q_probe)
            )
            raw_test = np.vstack((test_electric, test_traction))

            def gc_action(values: np.ndarray) -> np.ndarray:
                return _joint_cauchy_metric_action(
                    actual_h_mass, values, alpha=alpha, k0=cfg.k0
                )

            if core_snapshot is None:
                perp_test = raw_test
                core_whitening_error = None
            else:
                white_core = np.asarray(
                    core_snapshot["white_core"], dtype=np.complex128
                )
                core_whitening_error = _relative_matrix_error(
                    white_core.conj().T @ gc_action(white_core), np.eye(240)
                )
                if core_whitening_error > 1.0e-10:
                    raise AssertionError(
                        f"Q4b {side} snapshot whitening error "
                        f"{core_whitening_error:.3e}."
                    )

                def cperp(values: np.ndarray) -> np.ndarray:
                    return values - white_core @ (
                        white_core.conj().T @ gc_action(values)
                    )

                perp_test = cperp(raw_test)
            weighted_test = gc_action(perp_test)
            w_electric, w_traction = np.split(weighted_test, 2, axis=0)
            print("heartbeat: Q3c actual Schur factorization #1", flush=True)
            actual_action = build_hybrid_local_one_sided_schur_action(
                actual, actual_h_active, 1.0 if side == "bottom" else -1.0
            )
            actual_direct_source = actual_action.condense_rhs_columns(
                actual_loads.augmented_rhs
            )
            schur_hermitian = actual_action.apply_trace_hermitian_columns(
                w_traction
            )
            schur_left = np.vdot(
                actual_action.apply_trace_columns(e_probe)[:, 0], q_probe
            )
            schur_right = np.vdot(
                e_probe,
                actual_action.apply_trace_hermitian_columns(q_probe)[:, 0],
            )
            schur_pairing_defect = float(
                abs(schur_left - schur_right)
                / max(abs(schur_left), abs(schur_right), 1.0e-30)
            )
            if schur_pairing_defect > 1.0e-10:
                raise AssertionError("Q3c Schur Hermitian pairing failed.")
            direct_adjoint = (-actual_direct_source).conj().T @ w_traction
            direct_contribution_norms = np.linalg.norm(direct_adjoint, axis=0)
            if (
                not np.all(np.isfinite(direct_contribution_norms))
                or np.any(direct_contribution_norms[1:] <= 0.0)
            ):
                raise AssertionError("Q3c traction direct contribution is not covered.")
            u_h = w_electric + schur_hermitian
            adjoint_rhs = np.zeros(
                (buffer.global_size, 3), dtype=np.complex128
            )
            for column in range(3):
                adjoint_rhs[buffer_h_active, column] = mapper.dual(u_h[:, column])
            actual_action.destroy()
            actual_action = None
            print("heartbeat: destroyed actual Schur factorization #1", flush=True)

        print(f"heartbeat: factoring full {side} buffer matrix once", flush=True)
        buffer_solver = build_hybrid_local_full_matrix_solve_action(buffer)
        print("heartbeat: solving cut-only, incoming-only, and mixed columns", flush=True)
        states = buffer_solver.solve_columns(right_hand_sides)
        residuals = _full_augmented_residuals(buffer, right_hand_sides, states)
        if np.any(residuals > 1.0e-10):
            raise AssertionError(
                f"Buffer primal residuals {residuals.tolist()} exceed 1e-10."
            )
        zero_state = buffer_solver.solve_columns(
            np.zeros((buffer.global_size, 1), dtype=np.complex128)
        )
        zero_output_norm = float(np.linalg.norm(zero_state))
        if zero_output_norm != 0.0:
            raise AssertionError("Zero buffer source produced a nonzero state.")
        zero_electric = mapper.primal(zero_state[buffer_h_active, 0])
        zero_electric_norm = float(np.linalg.norm(zero_electric))
        buffer_h_states = states[buffer_h_active, :]
        electric = np.column_stack(
            [mapper.primal(buffer_h_states[:, column]) for column in range(3)]
        )
        if weighted_adjoint:
            if adjoint_rhs is None or direct_adjoint is None:
                raise RuntimeError("Q3c adjoint preparation is incomplete.")
            adjoint_states = buffer_solver.solve_hermitian_columns(adjoint_rhs)
            adjoint_residuals = _full_augmented_hermitian_residuals(
                buffer, adjoint_rhs, adjoint_states
            )
            if np.any(adjoint_residuals > 1.0e-9):
                raise AssertionError(
                    f"Q3c adjoint residuals {adjoint_residuals.tolist()} exceed 1e-9."
                )
            raw_cut = adjoint_states[cut_active, :]
            raw_incoming = (
                buffer_loads.augmented_rhs.conj().T @ adjoint_states
                + direct_adjoint
            )
            tstar_cut = (
                k0_squared / alpha * buffer_cut_mass.multiply_columns(raw_cut)
            )
            incoming_first = np.linalg.solve(incoming_factor, raw_incoming)
            tstar_incoming = (
                k0_squared
                / alpha
                * np.linalg.solve(incoming_factor.conj().T, incoming_first)
            )
            gs_tstar_cut = (
                alpha / k0_squared * buffer_cut_mass.solve_columns(tstar_cut)
            )
            gs_tstar_incoming = (
                alpha / k0_squared * incoming_gram @ tstar_incoming
            )
        buffer_solver.destroy()
        buffer_solver = None
        print("heartbeat: destroyed buffer factor", flush=True)

        print("heartbeat: Q3c actual Schur factorization #2", flush=True)
        actual_action = build_hybrid_local_one_sided_schur_action(
            actual, actual_h_active, 1.0 if side == "bottom" else -1.0
        )
        if not weighted_adjoint:
            actual_direct_source = actual_action.condense_rhs_columns(
                actual_loads.augmented_rhs
            )
        zero_traction = actual_action.apply_trace_columns(zero_electric)[:, 0]
        zero_traction_norm = float(np.linalg.norm(zero_traction))
        if zero_electric_norm != 0.0 or zero_traction_norm != 0.0:
            raise AssertionError("Zero source produced nonzero transferred e or q.")

        amplitudes = np.column_stack(
            (
                np.zeros(48, dtype=np.complex128),
                incoming_amplitude,
                incoming_amplitude,
            )
        )
        traction = actual_action.apply_trace_columns(electric) - (
            actual_direct_source @ amplitudes
        )
        if not np.all(np.isfinite(electric)) or not np.all(np.isfinite(traction)):
            raise AssertionError("Buffer transfer produced non-finite e/q output.")
        actual_action.destroy()
        actual_action = None
        print("heartbeat: destroyed actual Schur factorization #2", flush=True)
        if weighted_adjoint:
            source_eta = np.column_stack(
                (eta_cut, np.zeros(1200, dtype=np.complex128), eta_cut)
            )
            source_incoming = np.column_stack(
                (
                    np.zeros(48, dtype=np.complex128),
                    incoming_amplitude,
                    incoming_amplitude,
                )
            )
            raw_output = np.vstack((electric, traction))
            perp_output = (
                raw_output if core_snapshot is None else cperp(raw_output)
            )
            raw_test_metric = gc_action(raw_test)
            perp_test_metric = gc_action(perp_test)
            identity_defects: list[float] = []
            if core_snapshot is None:
                for column in range(3):
                    left = np.vdot(
                        perp_output[:, column], raw_test_metric[:, column]
                    )
                    right = np.vdot(
                        source_eta[:, column], gs_tstar_cut[:, column]
                    ) + np.vdot(
                        source_incoming[:, column],
                        gs_tstar_incoming[:, column],
                    )
                    identity_defects.append(
                        float(
                            abs(left - right)
                            / max(abs(left), abs(right), 1.0e-30)
                        )
                    )
                if max(identity_defects) > 1.0e-10:
                    raise AssertionError(
                        f"Q3c weighted identities {identity_defects} exceed 1e-10."
                    )
            else:
                raw_output_metric = gc_action(raw_output)
                perp_output_metric = gc_action(perp_output)
                gs_source_eta = (
                    alpha
                    / k0_squared
                    * buffer_cut_mass.solve_columns(source_eta)
                )
                gs_source_incoming = (
                    alpha / k0_squared * incoming_gram @ source_incoming
                )

                def metric_column_norms(
                    values: np.ndarray, metric_values: np.ndarray
                ) -> np.ndarray:
                    products = column_pairings(values, metric_values).real
                    return np.sqrt(np.maximum(products, 0.0))

                def column_pairings(
                    left_values: np.ndarray, right_values: np.ndarray
                ) -> np.ndarray:
                    return np.sum(left_values.conj() * right_values, axis=0)

                left = column_pairings(perp_output, raw_test_metric)
                right = column_pairings(
                    source_eta, gs_tstar_cut
                ) + column_pairings(source_incoming, gs_tstar_incoming)
                bridge = column_pairings(raw_output, perp_test_metric)
                composite_gap = np.abs(left - right)
                bridge_gap = np.abs(left - bridge)
                identity_defects = (
                    composite_gap
                    / np.maximum.reduce(
                        (np.abs(left), np.abs(right), np.full(3, 1.0e-30))
                    )
                ).tolist()
                bridge_defects = (
                    bridge_gap
                    / np.maximum.reduce(
                        (np.abs(left), np.abs(bridge), np.full(3, 1.0e-30))
                    )
                ).tolist()
                raw_output_norm = metric_column_norms(
                    raw_output, raw_output_metric
                )
                perp_output_norm = metric_column_norms(
                    perp_output, perp_output_metric
                )
                raw_test_norm = metric_column_norms(raw_test, raw_test_metric)
                perp_test_norm = metric_column_norms(
                    perp_test, perp_test_metric
                )
                source_norm = metric_column_norms(
                    np.vstack((source_eta, source_incoming)),
                    np.vstack((gs_source_eta, gs_source_incoming)),
                )
                tstar_norm = metric_column_norms(
                    np.vstack((tstar_cut, tstar_incoming)),
                    np.vstack((gs_tstar_cut, gs_tstar_incoming)),
                )
                composite_denominator = np.maximum(
                    np.maximum(
                        perp_output_norm * raw_test_norm,
                        source_norm * tstar_norm,
                    ),
                    1.0e-30,
                )
                bridge_denominator = np.maximum(
                    np.maximum(
                        perp_output_norm * raw_test_norm,
                        raw_output_norm * perp_test_norm,
                    ),
                    1.0e-30,
                )
                composite_normwise_errors = (
                    composite_gap / composite_denominator
                )
                bridge_normwise_errors = bridge_gap / bridge_denominator
                column_labels = ["cut_electric", "incoming_traction", "mixed"]
                q4b_pairing_diagnostics = {
                    "column_labels": column_labels,
                    "left": np.column_stack((left.real, left.imag)).tolist(),
                    "right": np.column_stack((right.real, right.imag)).tolist(),
                    "bridge": np.column_stack(
                        (bridge.real, bridge.imag)
                    ).tolist(),
                    "composite_absolute_gaps": composite_gap.tolist(),
                    "bridge_absolute_gaps": bridge_gap.tolist(),
                    "composite_normwise_denominators": (
                        composite_denominator.tolist()
                    ),
                    "bridge_normwise_denominators": bridge_denominator.tolist(),
                    "composite_normwise_backward_errors": (
                        composite_normwise_errors.tolist()
                    ),
                    "bridge_normwise_backward_errors": (
                        bridge_normwise_errors.tolist()
                    ),
                    "composite_scalar_cancellation_diagnostics": identity_defects,
                    "bridge_scalar_cancellation_diagnostics": bridge_defects,
                    "raw_output_gc_norms": raw_output_norm.tolist(),
                    "perp_output_gc_norms": perp_output_norm.tolist(),
                    "raw_test_gc_norms": raw_test_norm.tolist(),
                    "perp_test_gc_norms": perp_test_norm.tolist(),
                    "source_gs_norms": source_norm.tolist(),
                    "tstar_gs_norms": tstar_norm.tolist(),
                    "primal_relative_residuals": residuals.tolist(),
                    "adjoint_relative_residuals": adjoint_residuals.tolist(),
                    "schur_pairing_relative_defect": schur_pairing_defect,
                }
                print(
                    json.dumps(
                        {"q4b_pairing_diagnostics": q4b_pairing_diagnostics},
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
                if max(composite_normwise_errors) > 1.0e-10:
                    raise AssertionError(
                        "Q4b composite normwise backward errors "
                        f"{composite_normwise_errors} exceed 1e-10."
                    )
                if max(bridge_normwise_errors) > 1.0e-10:
                    raise AssertionError(
                        "Q4b bridge normwise backward errors "
                        f"{bridge_normwise_errors} exceed 1e-10."
                    )
            weighted_record = {
                "status": "pass",
                "identity_relative_defects": {
                    "cut_electric": identity_defects[0],
                    "incoming_traction": identity_defects[1],
                    "mixed": identity_defects[2],
                    "limit": 1.0e-10,
                },
                "adjoint_explicit_relative_residuals": adjoint_residuals.tolist(),
                "adjoint_residual_limit": 1.0e-9,
                "schur_hermitian_pairing_relative_defect": schur_pairing_defect,
                "schur_pairing_limit": 1.0e-10,
                "incoming_gram_rank_rcond_1e_10": incoming_rank,
                "incoming_gram_hermitian_relative_defect": (
                    incoming_gram_hermitian_defect
                ),
                "direct_contribution_norms": direct_contribution_norms.tolist(),
                "buffer_factorizations": 1,
                "actual_schur_factorizations": 2,
                "maximum_simultaneous_large_factors": 1,
            }
            if core_snapshot is not None:
                weighted_record.pop("identity_relative_defects")
                def named(values: list[float]) -> dict[str, float]:
                    return dict(zip(column_labels, values, strict=True))
                weighted_record.update(
                    {
                        "q4b_core_whitening_relative_error": (
                            core_whitening_error
                        ),
                        "q4b_composite_normwise_backward_errors": {
                            **named(composite_normwise_errors.tolist()),
                            "limit": 1.0e-10,
                        },
                        "q4b_bridge_normwise_backward_errors": {
                            **named(bridge_normwise_errors.tolist()),
                            "limit": 1.0e-10,
                        },
                        "q4b_composite_scalar_cancellation_diagnostics": named(
                            identity_defects
                        ),
                        "q4b_bridge_scalar_cancellation_diagnostics": named(
                            bridge_defects
                        ),
                        "q4b_pairing_diagnostics": q4b_pairing_diagnostics,
                    }
                )

        result = {
            "status": (
                f"partial_pass_q4b_{side}_m120_complement_weighted_adjoint"
                if core_snapshot is not None
                else (
                    f"partial_pass_q3c_{side}_weighted_adjoint"
                    if weighted_adjoint
                    else f"partial_pass_q3b_{side}_primal_transfer"
                )
            ),
            "live_buffer_transfer_side": side,
            "buffer": {
                "global_rows": buffer.global_size,
                "active_fe_rows": buffer.n_fe,
                "matrix_nnz": int(
                    buffer.A.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM).get(
                        "nz_used", 0.0
                    )
                ),
            },
            "actual": {
                "global_rows": actual.global_size,
                "active_fe_rows": actual.n_fe,
                "matrix_nnz": int(
                    actual.A.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM).get(
                        "nz_used", 0.0
                    )
                ),
            },
            "source_logical_shape": 1248,
            "output_logical_shape": 2400,
            "cut_active_rows": len(cut_active),
            "incoming_columns": len(buffer_loads.companions),
            "buffer_actual_companion_coordinates_match": (
                companion_coordinates_match
            ),
            "cut_physical_overlap_rows": len(overlap),
            "incoming_rhs_cut_max_abs": incoming_cut_max,
            "incoming_rhs_auxiliary_max_abs": incoming_aux_max,
            "mapper": {
                "source_active_rows": mapper.source_size,
                "target_active_rows": mapper.target_size,
                "z_shift": 0.0,
                "phase_applied": False,
                "orientation_blocks": len(_forward_blocks),
            },
            "primal_relative_residuals": {
                "cut_only": float(residuals[0]),
                "incoming_only": float(residuals[1]),
                "mixed": float(residuals[2]),
                "limit": 1.0e-10,
            },
            "zero_source_state_norm": zero_output_norm,
            "buffer_constant_source_norm": buffer_source_norm,
            "actual_constant_source_norm": actual_source_norm,
            "zero_source_e_norm": zero_electric_norm,
            "zero_source_q_norm": zero_traction_norm,
            "electric_column_norms": np.linalg.norm(electric, axis=0).tolist(),
            "traction_column_norms": np.linalg.norm(traction, axis=0).tolist(),
            "q_formula": "S_actual*e-f_actual_in*a",
            "direct_term_included": True,
            "dense_full_transfer_formed": False,
            "dense_interface_square_formed": False,
            "weighted_adjoint": weighted_record,
            "opposite_side": "not_run",
            "m120": (
                "qualified_local_projector_applied"
                if core_snapshot is not None
                else "not_run"
            ),
            "capacity": "not_run",
            "solve": "three_local_harmonic_columns_no_forward_pde",
        }
        return result
    finally:
        for mass_action in mass_actions:
            mass_action.destroy()
        if sampler_factor is not None:
            sampler_factor.destroy()
        if sampler_pc is not None:
            sampler_pc.destroy()
        if sampler_ksp is not None:
            sampler_ksp.destroy()
        if sampler_matrix is not None:
            sampler_matrix.destroy()
        if buffer_solver is not None:
            buffer_solver.destroy()
        if actual_action is not None:
            actual_action.destroy()
        if buffer is not None:
            buffer.destroy()
        if actual is not None:
            actual.destroy()
        if q5_temporary is not None:
            q5_temporary.cleanup()
        print(f"heartbeat: destroyed {side} buffer-transfer fixture", flush=True)


def build_bidirectional_transfers(
    source_edges: Iterable[EntityTrace],
    target_edges: Iterable[EntityTrace],
    source_faces: Iterable[EntityTrace],
    target_faces: Iterable[EntityTrace],
    source_plane: TracePlaneView,
    target_plane: TracePlaneView,
    *,
    degree: int,
    z_shift: float,
    tolerance: float,
) -> tuple[
    SparsePortTransfer,
    SparsePortTransfer,
    tuple[OrientedBlock, ...],
    tuple[OrientedBlock, ...],
]:
    """Construct forward and reverse independently from opposite geometry."""

    source_edges = tuple(source_edges)
    target_edges = tuple(target_edges)
    source_faces = tuple(source_faces)
    target_faces = tuple(target_faces)
    gate_p5_6x4_counts(source_edges, source_faces, source_plane)
    gate_p5_6x4_counts(target_edges, target_faces, target_plane)
    forward_blocks = build_original_transfer_blocks(
        source_edges,
        target_edges,
        source_faces,
        target_faces,
        degree=degree,
        z_shift=z_shift,
        tolerance=tolerance,
    )
    reverse_blocks = build_original_transfer_blocks(
        target_edges,
        source_edges,
        target_faces,
        source_faces,
        degree=degree,
        z_shift=-z_shift,
        tolerance=tolerance,
    )
    forward = build_primal_transfer(forward_blocks, source_plane, target_plane)
    reverse = build_primal_transfer(reverse_blocks, target_plane, source_plane)
    gate_constraint_identity(forward, forward_blocks, source_plane, target_plane)
    gate_constraint_identity(reverse, reverse_blocks, target_plane, source_plane)
    gate_bidirectional_roundtrip(forward, reverse)
    source_vector = np.arange(1, forward.source_size + 1, dtype=np.complex128)
    target_dual = 1.0j * np.arange(
        1, forward.target_size + 1, dtype=np.complex128
    )
    target_vector = np.arange(1, reverse.source_size + 1, dtype=np.complex128)
    source_dual = 1.0j * np.arange(
        1, reverse.target_size + 1, dtype=np.complex128
    )
    gate_dual_pairing(forward, source_vector, target_dual)
    gate_dual_pairing(reverse, target_vector, source_dual)
    return forward, reverse, forward_blocks, reverse_blocks


def _build_live_m120_joint_cauchy_projector(
    v9_endpoint_arrays: Mapping[str, np.ndarray] | None = None,
    live_setup: Mapping[str, Any] | None = None,
    selection_path: Path | None = None,
) -> tuple[
    dict[str, Any], dict[str, Any]
]:
    """Build Q4a evidence and retain only lightweight whitened-core snapshots."""

    comm = MPI.COMM_WORLD
    if comm.size != 1:
        raise RuntimeError("Q4a M120 projector qualification is serial-only.")
    cfg = replace(
        (live_setup["cfg"] if live_setup is not None else _authority_config()),
        incident_amplitude=0j,
    )
    systems: list[Any] = []
    maps: list[Any] = []
    masses: list[Any] = []
    coupling = None
    operators = positive = negative = None
    try:
        print("heartbeat: Q4a assembling actual bottom/top operators", flush=True)
        if live_setup is None:
            bottom = assemble_hybrid_local_dtn_system(
                cfg, "bottom", bottom_interface_z_nm=10.0,
                top_interface_z_nm=110.0, comm=comm, log=None,
            )
            systems.append(bottom)
            top = assemble_hybrid_local_dtn_system(
                cfg, "top", bottom_interface_z_nm=10.0,
                top_interface_z_nm=110.0, comm=comm, log=None,
            )
            systems.append(top)
        else:
            bottom = live_setup["bottom"]
            top = live_setup["top"]
        print("heartbeat: Q4a solving current M120 QEP basis", flush=True)
        _, spaces, operators, positive, negative, qep = _mode_basis(
            cfg, requested_modes=120, candidate_modes=240, comm=comm
        )
        print("heartbeat: Q4a building 100 nm internal coupling", flush=True)
        coupling = build_hybrid_internal_mode_coupling(
            cfg, spaces, positive, negative, bottom, top,
            length_nm=100.0,
            propagation_model="full3d_uniform_cg",
            modal_traction_model="scalar_cg_discrete_derivative",
            log=None,
        )
        if coupling.dense_interface_square_formed is not False:
            raise AssertionError("Q4a coupling formed a dense interface square.")
        factors = {
            "forward": np.asarray(coupling.propagation.forward.factors),
            "backward": np.asarray(coupling.propagation.backward.factors),
        }
        expected_source_indices = {
            "forward": tuple(range(120)),
            "backward": tuple(range(120, 240)),
        }
        for name in factors:
            block = getattr(coupling.propagation, name)
            if (
                block.length_nm != 100.0
                or block.mode_count != 120
                or block.propagation_model != "full3d_uniform_cg"
                or block.axial_cell_count != 10
                or tuple(block.source_indices) != expected_source_indices[name]
            ):
                raise AssertionError(f"Q4a {name} propagation identity changed.")
        c_negative = np.asarray(coupling.negative_trace_to_positive)
        alpha = 1.0 / 1250.0
        records: dict[str, Any] = {}
        v9_records: dict[str, Any] | None = None
        v9_projected: dict[str, dict[str, np.ndarray]] = {
            "right": {},
            "adjoint": {},
        }
        v9_metric_projected: dict[str, dict[str, np.ndarray]] = {
            "right": {},
            "adjoint": {},
        }
        if v9_endpoint_arrays is not None:
            block_ids = v9_endpoint_arrays["block_ids"]
            v9_records = {
                "block_count": int(np.unique(block_ids).size),
                "block_ids_sha256": hashlib.sha256(block_ids.tobytes()).hexdigest(),
                "endpoint_identity": v9_endpoint_arrays["endpoint_identity"],
                "map_gate": v9_endpoint_arrays["map_gate"],
                "sides": {},
            }
        snapshots: dict[str, dict[str, np.ndarray]] = {}
        global_grams: list[np.ndarray] = []
        for side, system in (("bottom", bottom), ("top", top)):
            print(f"heartbeat: Q4a building {side} strong map and H mass", flush=True)
            static = system.static_condensation
            if static is None:
                raise RuntimeError("Q4a requires assembly-time condensation.")
            z_pair = (-10.0, 10.0) if side == "bottom" else (110.0, 130.0)
            endpoints = identify_endpoint_active_rows(
                system.V,
                static.condensed,
                left_facets=_facets_at_z(system.V, z_pair[0], 1.0e-8),
                right_facets=_facets_at_z(system.V, z_pair[1], 1.0e-8),
            )
            h_original = endpoints.right_original if side == "bottom" else endpoints.left_original
            h_active = endpoints.right_active if side == "bottom" else endpoints.left_active
            external_original = endpoints.left_original if side == "bottom" else endpoints.right_original
            external_active = endpoints.left_active if side == "bottom" else endpoints.right_active
            interface_map = build_hybrid_strong_trace_interface_map(system, coupling)
            maps.append(interface_map)
            if interface_map.dense_interface_square_formed is not False:
                raise AssertionError(
                    f"{side} strong map formed a dense interface square."
                )
            external_mass, h_mass = build_endpoint_trace_mass_actions(
                system.V, system.local_mesh.mesh_data,
                static.condensed.trace_constraints,
                (
                    EndpointTraceMassSelection(system.local_mesh.external_facet_tag, external_original, external_active),
                    EndpointTraceMassSelection(system.local_mesh.interface_facet_tag, h_original, h_active),
                ),
            )
            masses.extend((external_mass, h_mass))
            if set(map(int, interface_map.interface_rows)) != set(map(int, h_active)):
                raise AssertionError(f"{side} strong-map and mass H-row sets differ.")
            prolongation = _petsc_rows(
                interface_map.right_prolongation, h_mass.active_rows
            )
            block = coupling.bottom if side == "bottom" else coupling.top
            positive_traction = _petsc_rows(block.positive_traction, h_mass.active_rows)
            negative_traction = _petsc_rows(block.negative_traction, h_mass.active_rows)
            normal_sign = block.local_fem_outward_normal_sign
            q_positive = -normal_sign * positive_traction
            q_negative = -normal_sign * negative_traction
            electric = np.column_stack((prolongation, prolongation @ c_negative))
            traction = np.column_stack((q_positive, q_negative))
            core = np.vstack((electric, traction))
            if core.shape != (2400, 240):
                raise AssertionError(f"{side} Q4a core shape is {core.shape}.")
            petrov_left = _petsc_rows(
                interface_map.petrov_left_columns, h_mass.active_rows
            )
            if petrov_left.shape != (1200, 120):
                raise AssertionError(
                    f"{side} positive Petrov columns have shape {petrov_left.shape}."
                )

            global_scale = np.concatenate(
                (
                    np.ones(120, dtype=np.complex128),
                    factors["backward"],
                )
                if side == "bottom"
                else (
                    factors["forward"],
                    np.ones(120, dtype=np.complex128),
                )
            )
            global_core = core * global_scale
            global_gc_core = _joint_cauchy_metric_action(
                h_mass, global_core, alpha=alpha, k0=cfg.k0
            )
            global_raw_gram = global_core.conj().T @ global_gc_core
            global_gram = 0.5 * (
                global_raw_gram + global_raw_gram.conj().T
            )
            global_grams.append(global_gram)
            global_eigenvalues = np.linalg.eigvalsh(global_gram)
            global_rank = int(
                np.count_nonzero(
                    global_eigenvalues
                    > (1.0e-10**2) * global_eigenvalues[-1]
                )
            )

            gc_core = _joint_cauchy_metric_action(h_mass, core, alpha=alpha, k0=cfg.k0)
            raw_gram = core.conj().T @ gc_core
            raw_defect = _relative_matrix_error(raw_gram, raw_gram.conj().T)
            if raw_defect > 1.0e-12:
                raise AssertionError(f"{side} raw core Gram Hermitian defect {raw_defect:.3e}.")
            gram = 0.5 * (raw_gram + raw_gram.conj().T)
            eigenvalues = np.linalg.eigvalsh(gram)
            rank = int(
                np.count_nonzero(
                    eigenvalues > (1.0e-10**2) * eigenvalues[-1]
                )
            )
            if rank != 240:
                raise AssertionError(f"{side} Q4a core rank is {rank}/240.")
            chol = np.linalg.cholesky(gram)
            white = np.linalg.solve(chol.conj(), core.T).T
            snapshots[side] = {
                "white_core": white.copy(),
                "actual_h_active": h_mass.active_rows.copy(),
                "electric_core": electric.copy(),
                "petrov_left": petrov_left,
            }
            if v9_endpoint_arrays is not None:
                endpoint = 1 if side == "bottom" else 0
                n = h_mass.shape[0]
                endpoint_slice = slice(endpoint * n, (endpoint + 1) * n)
                right_joint = np.vstack((
                    v9_endpoint_arrays["right_electric"][endpoint_slice],
                    -normal_sign * v9_endpoint_arrays["right_traction"][endpoint_slice],
                ))
                adjoint_joint = np.vstack((
                    v9_endpoint_arrays["adjoint_electric"][endpoint_slice],
                    -normal_sign * v9_endpoint_arrays["adjoint_traction"][endpoint_slice],
                ))

                def gc_action(
                    values: np.ndarray,
                    mass=h_mass,
                    alpha=alpha,
                    k0=cfg.k0,
                ) -> np.ndarray:
                    return _joint_cauchy_metric_action(
                        mass, values, alpha=alpha, k0=k0
                    )

                source_mass = v9_endpoint_arrays.get("source_h_mass")
                transfers = v9_endpoint_arrays.get("endpoint_transfers")
                if source_mass is None or transfers is None:
                    raise AssertionError("v9 endpoint mass/transfer identity is missing.")
                forward = transfers[side][0]
                probe = np.eye(n, 8, dtype=np.complex128)
                source_gram = probe.conj().T @ source_mass.multiply_columns(probe)
                target_probe = forward.primal(probe)
                target_gram = target_probe.conj().T @ h_mass.multiply_columns(target_probe)
                right_report, right_projected, right_metric = _v9_core_complement_data(
                    right_joint, white, gc_action
                )
                adjoint_report, adjoint_projected, adjoint_metric = _v9_core_complement_data(
                    adjoint_joint, white, gc_action
                )
                v9_projected["right"][side] = right_projected
                v9_projected["adjoint"][side] = adjoint_projected
                v9_metric_projected["right"][side] = right_metric
                v9_metric_projected["adjoint"][side] = adjoint_metric
                v9_records["sides"][side] = {
                    "right": right_report,
                    "adjoint": adjoint_report,
                    "h_mass_pullback_probe_relative_error": _relative_matrix_error(
                        target_gram, source_gram
                    ),
                }
                if (
                    v9_records["sides"][side]["h_mass_pullback_probe_relative_error"]
                    > 1.0e-8
                ):
                    raise AssertionError(f"{side} H-mass pullback probe failed.")
            white_identity = _relative_matrix_error(
                white.conj().T @ _joint_cauchy_metric_action(h_mass, white, alpha=alpha, k0=cfg.k0),
                np.eye(240),
            )
            decoder_identity = _relative_matrix_error(np.linalg.solve(gram, raw_gram), np.eye(240))
            projected_core = core @ np.linalg.solve(gram, raw_gram)
            projector_core = _relative_matrix_error(projected_core, core)
            probe = np.arange(1, 2401, dtype=np.complex128)[:, None] * (1.0 + 0.25j)
            def project(values: np.ndarray) -> np.ndarray:
                rhs = core.conj().T @ _joint_cauchy_metric_action(h_mass, values, alpha=alpha, k0=cfg.k0)
                return core @ np.linalg.solve(gram, rhs)
            projected = project(probe)
            idempotence = _relative_matrix_error(project(projected), projected)
            complement = probe - projected
            orthogonality = float(
                np.linalg.norm(core.conj().T @ _joint_cauchy_metric_action(h_mass, complement, alpha=alpha, k0=cfg.k0))
                / max(np.linalg.norm(core.conj().T @ _joint_cauchy_metric_action(h_mass, probe, alpha=alpha, k0=cfg.k0)), 1.0e-30)
            )
            probe_y = (
                np.arange(2400, 0, -1, dtype=np.complex128)[:, None]
                * (-0.5 + 0.75j)
            )
            projected_y = project(probe_y)
            pairing_left = np.vdot(
                projected,
                _joint_cauchy_metric_action(
                    h_mass, probe_y, alpha=alpha, k0=cfg.k0
                ),
            )
            pairing_right = np.vdot(
                probe,
                _joint_cauchy_metric_action(
                    h_mass, projected_y, alpha=alpha, k0=cfg.k0
                ),
            )
            self_adjoint = float(abs(pairing_left - pairing_right) / max(abs(pairing_left), abs(pairing_right), 1.0e-30))
            gates = (white_identity, decoder_identity, projector_core, idempotence, orthogonality, self_adjoint)
            if max(gates) > 1.0e-10:
                raise AssertionError(f"{side} Q4a projector gates {gates} exceed 1e-10.")
            records[side] = {
                "normal_sign": normal_sign,
                "core_shape": core.shape,
                "forward_columns": 120,
                "backward_columns": 120,
                "strong_mass_row_set_match": True,
                "electric_only_D_E_R_E_identity_error": interface_map.projection_identity_error,
                "raw_gram_hermitian_relative_defect": raw_defect,
                "gram_eigenvalue_min": float(eigenvalues[0]),
                "gram_eigenvalue_max": float(eigenvalues[-1]),
                "gram_condition": float(eigenvalues[-1] / eigenvalues[0]),
                "gram_rank_rcond_1e_10": rank,
                "rank_semantics": "metric_weighted_basis_singular_values",
                "global_restriction_diagnostic": {
                    "rank_rcond_1e_10": global_rank,
                    "gate": False,
                },
                "cholesky": "pass",
                "white_identity_relative_error": white_identity,
                "joint_decoder_identity_relative_error": decoder_identity,
                "projector_core_relative_error": projector_core,
                "projector_idempotence_relative_error": idempotence,
                "projector_orthogonality_relative_error": orthogonality,
                "projector_gc_self_adjoint_pairing_relative_error": self_adjoint,
                "h_mass": {
                    "shape": h_mass.shape,
                    "hermitian_relative_defect": h_mass.hermitian_relative_defect,
                    "constraint_action_relative_error": h_mass.constraint_action_relative_error,
                    "solve_relative_residual": h_mass.solve_relative_residual,
                },
            }
        if v9_endpoint_arrays is not None:
            selection = select_v9_block_prefixes(
                v9_projected["right"],
                v9_projected["adjoint"],
                v9_endpoint_arrays["block_ids"],
                v9_metric_projected["right"],
                v9_metric_projected["adjoint"],
                requested=(40, 80, 120),
            )
            v9_records["selection"] = {
                "prefixes": selection["prefixes"],
                "uniform_full_trace_diagnostic": "not_a_reachable_physics_gate",
                "reachable_physics_gate": "not_run",
                "reduced_solve_holdout": "not_run",
            }
            if selection_path is not None:
                npz_arrays = {
                    "block_ids": np.asarray(v9_endpoint_arrays["block_ids"], dtype=np.int64),
                    "bottom_right": v9_projected["right"]["bottom"],
                    "bottom_adjoint": v9_projected["adjoint"]["bottom"],
                    "top_right": v9_projected["right"]["top"],
                    "top_adjoint": v9_projected["adjoint"]["top"],
                }
                np.savez(selection_path, **npz_arrays)
                v9_records["selection_artifact"] = {
                    "path": str(selection_path),
                    "sha256": _sha256(selection_path),
                    "bytes": selection_path.stat().st_size,
                    "shapes": {
                        name: list(np.asarray(values).shape)
                        for name, values in npz_arrays.items()
                    },
                }
            snapshots["b1"] = {
                "right_projected": v9_projected["right"],
                "adjoint_projected": v9_projected["adjoint"],
                "right_multipliers": np.asarray(
                    v9_endpoint_arrays["right_multipliers"], dtype=np.complex128
                ).copy(),
                "adjoint_multipliers": np.asarray(
                    v9_endpoint_arrays["adjoint_multipliers"], dtype=np.complex128
                ).copy(),
                "block_ids": np.asarray(
                    v9_endpoint_arrays["block_ids"], dtype=np.int64
                ).copy(),
                "factors": {name: values.copy() for name, values in factors.items()},
                "selection": selection,
            }
        combined_global_gram = global_grams[0] + global_grams[1]
        combined_global_eigenvalues = np.linalg.eigvalsh(
            0.5 * (combined_global_gram + combined_global_gram.conj().T)
        )
        combined_global_rank = int(
            np.count_nonzero(
                combined_global_eigenvalues
                > (1.0e-10**2) * combined_global_eigenvalues[-1]
            )
        )
        record = {
            "status": (
                "partial_block_prefix_selection"
                if v9_records is not None
                else "partial_pass_q4a_m120_joint_cauchy_projector"
            ),
            "mode_count_per_direction": 120,
            "qep": qep,
            "propagation": {
                name: {
                    "direction": block.direction,
                    "length_nm": block.length_nm,
                    "mode_count": block.mode_count,
                    "propagation_model": block.propagation_model,
                    "axial_cell_count": block.axial_cell_count,
                    "source_indices_identity": True,
                    "source_index_first": int(block.source_indices[0]),
                    "source_index_last": int(block.source_indices[-1]),
                    "source_index_unique_count": len(set(block.source_indices)),
                    "exact_zero_count": int(np.count_nonzero(values == 0.0)),
                    "abs_factor_ge_1e_5_count": int(
                        np.count_nonzero(np.abs(values) >= 1.0e-5)
                    ),
                    "abs_factor_ge_1e_10_count": int(
                        np.count_nonzero(np.abs(values) >= 1.0e-10)
                    ),
                    "abs_factor_min": float(np.min(np.abs(values))),
                    "abs_factor_max": float(np.max(np.abs(values))),
                }
                for name, values in factors.items()
                for block in (getattr(coupling.propagation, name),)
            },
            "combined_two_end_global_restriction_rank_rcond_1e_10": (
                combined_global_rank
            ),
            "sides": records,
            "dense_interface_square_formed": bool(
                coupling.dense_interface_square_formed
                or any(item.dense_interface_square_formed for item in maps)
            ),
            "forward_solve": "not_run",
            "q4b": "not_run",
            "capacity": "not_run",
            "v9_core_complement": v9_records or "not_run",
        }
        return record, snapshots
    finally:
        for mass in reversed(masses):
            mass.destroy()
        for interface_map in reversed(maps):
            interface_map.destroy()
        if coupling is not None:
            coupling.destroy()
        if negative is not None:
            negative.destroy()
        if positive is not None:
            positive.destroy()
        if operators is not None:
            operators.destroy()
        for system in reversed(systems):
            system.destroy()


def run_live_v9_core_complement_rank(
    json_path: Path = V9_MODE_POOL_JSON,
    npz_path: Path = V9_MODE_POOL_NPZ,
    selection_path: Path | None = None,
) -> dict[str, Any]:
    """Measure v9 Cauchy rank after the live M120 G_C projection."""

    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("run_live_v9_core_complement_rank is serial-only.")
    pool = load_v9_mode_pool(json_path, npz_path)
    work_dir = tempfile.TemporaryDirectory(prefix="task036-v9-core-")
    zero_cfg = replace(_authority_config(), incident_amplitude=0j)
    setup = _build_d1_local_factor_setup(
        work_dir,
        case_cfg=zero_cfg,
        endpoint_comms=(MPI.COMM_WORLD, MPI.COMM_WORLD),
    )
    chain = None
    source_mass_actions: tuple[Any, ...] = ()
    try:
        chain, _, _, _ = _build_d1_trace_chain(setup)
        source_mass_actions = build_endpoint_trace_mass_actions(
            setup["V"],
            setup["one_cell_mesh"],
            setup["condensed"].trace_constraints,
            (
                EndpointTraceMassSelection(
                    setup["one_cell_cfg"].tags.z_min,
                    setup["one_cell_rows"].left_original,
                    setup["one_cell_rows"].left_active,
                ),
                EndpointTraceMassSelection(
                    setup["one_cell_cfg"].tags.z_max,
                    setup["one_cell_rows"].right_original,
                    setup["one_cell_rows"].right_active,
                ),
            ),
        )
        arrays = v9_endpoint_cauchy_arrays(
            chain.cell_action, pool, setup["d1_endpoint_transfers"]
        )
        arrays["source_h_mass"] = source_mass_actions[0]
        record, _ = _build_live_m120_joint_cauchy_projector(
            arrays, live_setup=setup, selection_path=selection_path
        )
        return {
            "status": record["status"],
            "source_sha": pool["record"]["source"]["sha"],
            "raw_columns": 184,
            "q4a": record["v9_core_complement"],
            "capacity_selection": "partial_block_prefix_selection",
        }
    finally:
        for mass in reversed(source_mass_actions):
            mass.destroy()
        if chain is not None:
            chain.destroy()
        setup["bottom"].destroy()
        setup["top"].destroy()
        setup["condensed"].destroy()
        if hasattr(setup["one_cell_floquet"].mpc, "destroy"):
            setup["one_cell_floquet"].mpc.destroy()
        work_dir.cleanup()


def run_live_b1_reachable_physics_gate() -> dict[str, Any]:
    """Measure A004-S reduced B1 prefixes from one shared trace-chain setup."""

    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("run_live_b1_reachable_physics_gate is serial-only.")
    pool = load_v9_mode_pool()
    work_dir = tempfile.TemporaryDirectory(prefix="task036-b1-")
    setup = _build_d1_local_factor_setup(work_dir)
    bottom = setup["bottom"]
    top = setup["top"]
    bottom_action = setup["bottom_action"]
    top_action = setup["top_action"]
    chain = None
    source_mass_actions: tuple[Any, ...] = ()
    try:
        chain, _, bottom_transfer, top_transfer = _build_d1_trace_chain(setup)
        source_mass_actions = build_endpoint_trace_mass_actions(
            setup["V"],
            setup["one_cell_mesh"],
            setup["condensed"].trace_constraints,
            (
                EndpointTraceMassSelection(
                    setup["one_cell_cfg"].tags.z_min,
                    setup["one_cell_rows"].left_original,
                    setup["one_cell_rows"].left_active,
                ),
                EndpointTraceMassSelection(
                    setup["one_cell_cfg"].tags.z_max,
                    setup["one_cell_rows"].right_original,
                    setup["one_cell_rows"].right_active,
                ),
            ),
        )
        arrays = v9_endpoint_cauchy_arrays(
            chain.cell_action,
            pool,
            {
                "bottom": (
                    bottom_transfer,
                    setup["d1_endpoint_transfers"]["bottom"][1],
                ),
                "top": (
                    top_transfer,
                    setup["d1_endpoint_transfers"]["top"][1],
                ),
            },
        )
        arrays["source_h_mass"] = source_mass_actions[0]
        q4a_record, snapshots = _build_live_m120_joint_cauchy_projector(
            arrays, live_setup=setup
        )
        b1 = snapshots.pop("b1")
        compact_blocks, compact_record = chain.build_compact_trace_blocks(
            column_block_size=16
        )
        actual_rhs, rhs_record, _, _ = _build_d1_actual_rhs(
            bottom,
            top,
            bottom_action,
            top_action,
            chain,
            bottom_transfer,
            top_transfer,
        )
        prefix_data = b1["selection"]["prefixes"]
        block_ids = b1["block_ids"]
        ordering = b1["selection"]["ordering"]

        def prefix_indices(target: int) -> np.ndarray:
            if target == 0:
                return np.empty(0, dtype=np.int64)
            prefix = prefix_data[str(target)]
            block_count = int(prefix["selected_block_count"])
            blocks = ordering[:block_count]
            block_hash = hashlib.sha256(
                np.asarray(blocks, dtype=np.int64).tobytes()
            ).hexdigest()
            if block_hash != prefix["selected_block_ids_sha256"]:
                raise AssertionError("B1 prefix block identity changed.")
            indices = np.concatenate(
                [np.flatnonzero(block_ids == block) for block in blocks]
            ) if block_count else np.empty(0, dtype=np.int64)
            index_hash = hashlib.sha256(indices.tobytes()).hexdigest()
            if index_hash != prefix["selected_indices_sha256"]:
                raise AssertionError("B1 prefix column identity changed.")
            return indices

        max_indices = prefix_indices(120)
        for target in (40, 80, 120):
            if not np.array_equal(prefix_indices(target), max_indices[: len(prefix_indices(target))]):
                raise AssertionError("B1 selection prefixes are not nested.")

        def stable_end_factors(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
            values = np.asarray(values, dtype=np.complex128)
            bottom_factor = np.ones_like(values)
            top_factor = np.ones_like(values)
            bounded = np.abs(values) <= 1.0
            top_factor[bounded] = values[bounded] ** 10
            bottom_factor[~bounded] = values[~bounded] ** -10
            return bottom_factor, top_factor

        factors = b1["factors"]
        bottom_snapshot = snapshots["bottom"]
        top_snapshot = snapshots["top"]
        right_core_bottom = bottom_snapshot["electric_core"] * np.concatenate(
            (np.ones(120, dtype=np.complex128), factors["backward"])
        )
        right_core_top = top_snapshot["electric_core"] * np.concatenate(
            (factors["forward"], np.ones(120, dtype=np.complex128))
        )
        right_bottom_factor, right_top_factor = stable_end_factors(
            b1["right_multipliers"][max_indices]
        )
        adjoint_bottom_factor, adjoint_top_factor = stable_end_factors(
            b1["adjoint_multipliers"][max_indices]
        )
        right_corrector_bottom = b1["right_projected"]["bottom"][:1200, max_indices]
        right_corrector_top = b1["right_projected"]["top"][:1200, max_indices]
        adjoint_corrector_bottom = b1["adjoint_projected"]["bottom"][:1200, max_indices]
        adjoint_corrector_top = b1["adjoint_projected"]["top"][:1200, max_indices]
        right_bottom_local = np.hstack(
            (right_core_bottom, right_corrector_bottom * right_bottom_factor)
        )
        right_top_local = np.hstack(
            (right_core_top, right_corrector_top * right_top_factor)
        )
        left_bottom_local = np.hstack(
            (
                bottom_snapshot["petrov_left"],
                np.zeros((1200, 120), dtype=np.complex128),
                adjoint_corrector_bottom * adjoint_bottom_factor,
            )
        )
        left_top_local = np.hstack(
            (
                np.zeros((1200, 120), dtype=np.complex128),
                top_snapshot["petrov_left"],
                adjoint_corrector_top * adjoint_top_factor,
            )
        )
        bottom_reverse = setup["d1_endpoint_transfers"]["bottom"][1]
        top_reverse = setup["d1_endpoint_transfers"]["top"][1]
        right_endpoint = np.vstack(
            (
                bottom_reverse.primal(right_bottom_local),
                top_reverse.primal(right_top_local),
            )
        )
        left_endpoint = np.vstack(
            (
                bottom_reverse.primal(left_bottom_local),
                top_reverse.primal(left_top_local),
            )
        )
        if right_endpoint.shape != left_endpoint.shape or right_endpoint.shape != (
            2400,
            360,
        ):
            raise AssertionError(
                "Canonical B1 endpoint trial/test columns are not (2400, 360)."
            )
        trace_basis, endpoint_action, extension_record = build_b1_harmonic_extension(
            compact_blocks, right_endpoint
        )
        endpoint_rhs = np.vstack((actual_rhs[:1200], actual_rhs[-1200:]))
        prefixes: dict[str, Any] = {}
        for target in (0, 40, 80, 120):
            count = len(prefix_indices(target))
            columns = 240 + count
            reduced = solve_b1_reduced_petrov(
                trace_basis[:, :columns],
                right_endpoint[:, :columns],
                endpoint_action[:, :columns],
                left_endpoint[:, :columns],
                endpoint_rhs,
                actual_rhs,
                chain.apply_columns,
            )
            reduced.pop("lifted_trace")
            prefix = prefix_data[str(target)] if target else {
                "selected_block_count": 0,
                "raw_column_count": 0,
            }
            prefixes[str(target)] = {
                "requested_r": target,
                "selected_raw_corrector_columns": count,
                "selected_block_count": int(prefix["selected_block_count"]),
                "selected_block_ids_sha256": prefix.get("selected_block_ids_sha256"),
                "raw_checkpoint_dimension": 240 + count,
                "d_port": int(reduced["trial_rank"]),
                **reduced,
            }
        return {
            "status": "partial_b1_reachable_physics_measurement",
            "q4a": q4a_record,
            "compact_trace": compact_record,
            "harmonic_extension": extension_record,
            "actual_rhs": rhs_record,
            "prefixes": prefixes,
            "endpoint_coordinates": {
                "canonicalized": True,
                "map": "reverse.primal",
            },
            "reachable_physics_gate": "not_run",
            "reduced_solve_holdout": "not_run",
            "capacity": "not_run",
            "global_dense_endpoint_square_formed": False,
        }
    finally:
        for mass in reversed(source_mass_actions):
            mass.destroy()
        if chain is not None:
            chain.destroy()
        bottom.destroy()
        top.destroy()
        setup["condensed"].destroy()
        if hasattr(setup["one_cell_floquet"].mpc, "destroy"):
            setup["one_cell_floquet"].mpc.destroy()
        work_dir.cleanup()


def run_live_m120_joint_cauchy_projector_fixture() -> dict[str, Any]:
    """Qualify the current M120 joint-Cauchy core projector on both H planes."""

    record, _snapshots = _build_live_m120_joint_cauchy_projector()
    return record


def run_live_m120_complement_weighted_adjoint_fixture() -> dict[str, Any]:
    """Qualify both per-port complement transfers with the full adjoint."""

    q4a_record, snapshots = _build_live_m120_joint_cauchy_projector()
    side_records: dict[str, Any] = {}
    for side in ("bottom", "top"):
        snapshot = snapshots.pop(side)
        side_records[side] = run_live_buffer_transfer_fixture(
            side, weighted_adjoint=True, core_snapshot=snapshot
        )
        del snapshot
    return {
        "status": "partial_pass_q4b_m120_complement_weighted_adjoint_both_sides",
        "q4a": q4a_record,
        "sides": side_records,
        "capacity": "not_run",
        "forward_solve": "not_run",
    }


def run_live_m120_randomized_capacity_fixture(
    side: str | None = None,
) -> dict[str, Any]:
    """Run the frozen randomized singular-tail certification."""

    q4a_record, snapshots = _build_live_m120_joint_cauchy_projector()
    sides: dict[str, Any] = {}
    requested_sides = (side,) if side is not None else ("bottom", "top")
    for current_side in requested_sides:
        snapshot = snapshots.pop(current_side)
        sides[current_side] = run_live_buffer_transfer_fixture(
            current_side,
            weighted_adjoint=True,
            core_snapshot=snapshot,
            randomized_capacity=True,
        )
        print(
            "heartbeat: Q5 side result "
            + json.dumps(
                {
                    "side": current_side,
                    "status": sides[current_side]["status"],
                    "certified_rank_1e_8": sides[current_side]["certified_ranks"][
                        str(1.0e-8)
                    ],
                    "holdout_valid": sides[current_side][
                        "holdout_direct_quadratic_valid"
                    ],
                    "denominator_valid": sides[current_side][
                        "primal_range_denominator_valid"
                    ],
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        del snapshot
    if side is not None:
        return sides[side]
    ranks_1e_8 = [
        sides[current_side]["certified_ranks"][str(1.0e-8)]
        for current_side in ("bottom", "top")
    ]
    reached = all(
        sides[current_side]["status"].startswith("partial_pass_q5_")
        and sides[current_side]["holdout_direct_quadratic_valid"] is True
        and sides[current_side]["primal_range_denominator_valid"] is True
        and isinstance(sides[current_side]["certified_ranks"][str(1.0e-8)], int)
        for current_side in ("bottom", "top")
    )
    return {
        "status": (
            "partial_pass_q5_m120_randomized_capacity_both_sides"
            if reached
            else "controlled_stop_q5_certified_tail_1e_8_not_reached"
        ),
        "q4a_status": q4a_record["status"],
        "sides": sides,
        "r_frozen": max(ranks_1e_8) if reached else "not_reached",
        "equal_dimension": "not_run",
        "shifted_dominance": "not_run",
        "resource_preflight": "not_run",
        "forward_pde": "not_run",
    }




def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--describe-live-entry",
        action="store_true",
        help="print the direct fixture entry point without running a PDE",
    )
    parser.add_argument("--live-side", choices=("bottom", "top"))
    parser.add_argument(
        "--live-schur-q-side", choices=("bottom", "top")
    )
    parser.add_argument("--live-incoming-side", choices=("bottom", "top"))
    parser.add_argument("--live-buffer-transfer-side", choices=("bottom", "top"))
    parser.add_argument(
        "--live-weighted-adjoint-side", choices=("bottom", "top")
    )
    parser.add_argument(
        "--live-m120-joint-cauchy-projector",
        action="store_true",
    )
    parser.add_argument(
        "--live-m120-complement-weighted-adjoint",
        action="store_true",
    )
    parser.add_argument(
        "--live-m120-randomized-capacity",
        action="store_true",
    )
    parser.add_argument(
        "--live-m120-randomized-capacity-side",
        choices=("bottom", "top"),
    )
    parser.add_argument(
        "--live-d1a-materialization-timing",
        action="store_true",
    )
    parser.add_argument(
        "--live-d1b-assemble-only",
        action="store_true",
    )
    parser.add_argument(
        "--live-d1c-direct-factor-solve",
        action="store_true",
    )
    parser.add_argument(
        "--live-d2-block-direct-solve",
        action="store_true",
    )
    parser.add_argument(
        "--live-d2-block-direct-solve-mpi-endpoints",
        action="store_true",
        help="opt in to paired MPI4 endpoint direct execution on MPI8",
    )
    parser.add_argument(
        "--d2-case",
        choices=(
            "A004-S",
            "A001-P",
            "A002-P",
            "A003-P",
            "A004-P",
            "A007-P",
            "A008-P",
            "A046-P",
            "A049-P",
        ),
        default="A004-S",
        help="fixed D2 direct anchor; default preserves the A004-S path",
    )
    parser.add_argument("--d2-current-full3d-record", type=Path)
    parser.add_argument("--d2-current-full3d-reference-root", type=Path)
    parser.add_argument("--d2-output-root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.live_m120_randomized_capacity:
        print(
            json.dumps(
                run_live_m120_randomized_capacity_fixture(),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.live_m120_randomized_capacity_side is not None:
        print(
            json.dumps(
                run_live_m120_randomized_capacity_fixture(
                    side=args.live_m120_randomized_capacity_side
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.live_d1a_materialization_timing:
        result = run_live_d1a_materialization_timing()
        if MPI.COMM_WORLD.rank == 0:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.live_d1b_assemble_only:
        result = run_live_d1b_assemble_only()
        if MPI.COMM_WORLD.rank == 0:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.live_d1c_direct_factor_solve:
        result = run_live_d1c_direct_factor_solve()
        if MPI.COMM_WORLD.rank == 0:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.live_d2_block_direct_solve:
        result = run_live_d2_block_direct_solve(
            args.d2_case,
            current_full3d_record=args.d2_current_full3d_record,
            current_full3d_reference_root=args.d2_current_full3d_reference_root,
            d2_output_root=args.d2_output_root,
        )
        if MPI.COMM_WORLD.rank == 0:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.live_d2_block_direct_solve_mpi_endpoints:
        result = run_live_d2_block_direct_solve(
            args.d2_case,
            mpi_endpoints=True,
            current_full3d_record=args.d2_current_full3d_record,
            current_full3d_reference_root=args.d2_current_full3d_reference_root,
            d2_output_root=args.d2_output_root,
        )
        if MPI.COMM_WORLD.rank == 0:
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    if args.live_m120_complement_weighted_adjoint:
        print(
            json.dumps(
                run_live_m120_complement_weighted_adjoint_fixture(),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.live_m120_joint_cauchy_projector:
        print(
            json.dumps(
                run_live_m120_joint_cauchy_projector_fixture(),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.live_weighted_adjoint_side is not None:
        print(
            json.dumps(
                run_live_buffer_transfer_fixture(
                    args.live_weighted_adjoint_side,
                    weighted_adjoint=True,
                ),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.live_buffer_transfer_side is not None:
        print(
            json.dumps(
                run_live_buffer_transfer_fixture(args.live_buffer_transfer_side),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.live_incoming_side is not None:
        print(
            json.dumps(
                run_live_incoming_fixture(args.live_incoming_side),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.live_schur_q_side is not None:
        print(
            json.dumps(
                run_live_schur_q_fixture(args.live_schur_q_side),
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.live_side == "bottom":
        print(json.dumps(run_live_bottom_fixture(), indent=2, sort_keys=True))
        return 0
    if args.live_side == "top":
        print(json.dumps(run_live_top_fixture(), indent=2, sort_keys=True))
        return 0
    if args.describe_live_entry:
        print(
            "entity_traces_from_live_space(V, degree=5, "
            "plane_facets=endpoint_facets)"
        )
        return 0
    raise SystemExit(
        "fail-closed: no formal live assembly fixture is wired to this CLI"
    )


if __name__ == "__main__":
    raise SystemExit(main())
