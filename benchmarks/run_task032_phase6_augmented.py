from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

try:
    import resource
except ModuleNotFoundError:  # pragma: no cover - Windows host path
    resource = None

from benchmarks.task035c_p6_h10_gates import (
    TASK035C_P6_H10_BACKENDS,
    TASK035C_P6_H10_MODE_COUNTS,
    TASK035C_P6_H10_MPI_SIZES,
    task035c_p6_h10_full3d_reference_gate,
    task037b_h1_pinned_full3d_reference_gate,
    task035c_p6_h10_preflight_authority_gate,
    valid_hex_digest,
)
from benchmarks.task032_final_gates import (
    _all_formal_true,
    _exact_traction_gate,
)
from src.common.config_3d import (
    ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
    STANDARD_FULL_ASSEMBLY_BACKEND,
    target_stage4_config,
)
from src.common.distributed_matrix_diagnostics import (
    distributed_active_column_count,
)
from src.coupling.hybrid_internal_modes import (
    build_hybrid_internal_mode_coupling,
)
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    PoyntingFluxEvaluator,
    build_biorthogonal_mode_basis,
    pair_reciprocal_mode_bases,
    select_passive_direction_modes,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from src.postprocessing.hybrid_field_reconstruction import (
    ModalFieldReconstructor,
    compare_selected_planes_to_reference,
    hybrid_volume_absorption,
    interface_field_continuity,
)
from src.solvers.hybrid_fem_modal_augmented_direct import (
    HybridAugmentedLayout,
    build_hybrid_augmented_direct_system,
    evaluate_hybrid_augmented_solution,
    internal_modal_rhs_correction,
    solve_hybrid_augmented_direct,
)
from src.solvers.hybrid_fem_modal_block_ldu import (
    HybridBlockActionSystem,
    HybridBlockLduPhysicalSolution,
    _HybridBlockLduOracleLocalSystem,
    create_exact_block_ldu_preconditioner,
    create_g_only_block_ldu_preconditioner,
    modal_block_diagnostic,
    solve_exact_block_ldu,
)
from src.solvers.hybrid_fem_modal_iterative import create_hybrid_assembled_block_action
from src.solvers.hybrid_fem_modal_schur_direct import (
    _factor_local,
    _local_factor_inventory,
    build_hybrid_modal_schur_direct_system,
    build_hybrid_modal_schur_memory_minimal_system,
    solve_hybrid_modal_schur_direct,
)
from src.solvers.hybrid_local_iterative_inverse import (
    build_hybrid_local_iterative_inverse,
)
from src.solvers.hybrid_local_dtn_action import assemble_hybrid_local_dtn_action_system
from src.solvers.hybrid_local_dtn import assemble_hybrid_local_dtn_system
from src.solvers.hybrid_static_field_recovery import recover_hybrid_static_local_field
from src.solvers.condensed_dtn import (
    build_explicit_condensed_operator,
    condensed_rhs,
    extract_petsc_condensed_blocks,
    recover_petsc_auxiliary,
)
from src.solvers.hybrid_status import hybrid_p_disposition
from src.solvers.common_3d_solve import (
    _petsc_factor_inventory,
    _petsc_matrix_stats,
)
from src.solvers.common_3d_utils import _trim_process_heap


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "benchmarks"
    / "artifacts"
    / "cases"
    / "080"
    / "phase6"
    / "hybrid_augmented_research.json"
)
REFERENCE_BY_DEGREE_AND_H = {
    (2, 5.0): ROOT
    / "benchmarks"
    / "cases"
    / "080_hybrid_fem_modal_direct_baseline"
    / "records"
    / "full3d_h5_reference.json",
    (2, 3.0): ROOT
    / "benchmarks"
    / "cases"
    / "080_hybrid_fem_modal_direct_baseline"
    / "records"
    / "full3d_h3_reference.json",
    (3, 5.0): ROOT
    / "benchmarks"
    / "cases"
    / "091_hybrid_hp_adaptivity_feasibility"
    / "records"
    / "stage3_p3_h5"
    / "full3d_reference.json",
}


def _discrete_axial_qualification_scope(
    propagation_model: str,
    traction_model: str,
) -> dict[str, Any]:
    """Expose the fail-closed scope of the Task035c discrete axial symbols."""

    selected = (
        propagation_model == "full3d_uniform_cg"
        or traction_model == "scalar_cg_discrete_derivative"
    )
    return {
        "selected": selected,
        "status": (
            "qualified_only_for_listed_scope"
            if selected
            else "not_selected_ordinary_continuous_symbols"
        ),
        "qualified": [
            "fixed rectangular block grating",
            "structured tensor-product mesh",
            "axis-aligned first-order affine hexahedra",
            "uniform z segmentation in the modal middle region",
            "one axial h for the scalar CG(p) chain",
            "supported axial degree p1-p6",
            "complex128",
            "Floquet periodicity",
            "sparse auxiliary DtN",
            "direct standard/static Full3D and Hybrid",
        ],
        "not_qualified": [
            "nonuniform z spacing",
            "locally refined or hanging-node hexa mesh",
            "curved or distorted hexahedra",
            "high-order curved geometry mapping",
            "tetrahedral static condensation",
            "hexa/tetra/prism/pyramid mixed meshes",
            "irregular geometry",
            "production automatic hp adaptivity",
        ],
        "failure_policy": (
            "unsupported meshes and inconsistent propagation/traction "
            "combinations fail closed; no fallback is permitted"
        ),
    }


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _source_provenance(
    comm: MPI.Intracomm,
    verified_clean_sha: str | None,
    allow_dirty_research: bool,
) -> dict[str, Any]:
    if comm.rank == 0:
        head = _git("rev-parse", "HEAD")
        branch = _git("branch", "--show-current")
        tracked_status = _git("status", "--porcelain", "--untracked-files=all")
        payload = (head, branch, tracked_status)
    else:
        payload = None
    head, branch, tracked_status = comm.bcast(payload, root=0)
    if head is None or tracked_status is None:
        raise SystemExit("Cannot verify Task32 Phase6 source provenance.")
    if verified_clean_sha is not None:
        verified = verified_clean_sha.strip().lower()
        if len(verified) != 40 or any(
            character not in "0123456789abcdef" for character in verified
        ):
            raise SystemExit("--verified-clean-sha must be a full Git SHA.")
        if head.lower() != verified:
            raise SystemExit(
                f"Clean-source attestation {verified} does not match HEAD {head}."
            )
        if tracked_status:
            raise SystemExit(
                "Tracked source is dirty despite --verified-clean-sha. "
                "Commit the implementation before a qualifying run."
            )
        tracked_dirty = False
        verification = "local_full_sha_and_tracked_status"
    else:
        if allow_dirty_research:
            tracked_dirty = True
            verification = "dirty_research_opt_in_with_status_scan"
        elif tracked_status:
            raise SystemExit(
                "Tracked source is dirty. Commit Phase6 code first or pass "
                "--allow-dirty-research for a non-qualifying diagnostic."
            )
        else:
            tracked_dirty = False
            verification = "local_git_status"
    return {
        "commit_sha": head,
        "branch": branch,
        "git_dirty": tracked_dirty,
        "tracked_source_dirty": tracked_dirty,
        "verification": verification,
        "verified_clean_sha": verified_clean_sha,
    }


def _verify_source_stable_at_end(
    comm: MPI.Intracomm,
    start: dict[str, Any],
    verified_clean_sha: str | None,
    allow_dirty_research: bool,
) -> None:
    """Require the same tracked-source state at the end of a formal shard."""

    end = _source_provenance(comm, verified_clean_sha, allow_dirty_research)
    if end["commit_sha"] != start["commit_sha"]:
        raise SystemExit("Tracked source HEAD changed during the Hybrid run.")
    if not allow_dirty_research and end["tracked_source_dirty"]:
        raise SystemExit("Tracked source became dirty during the Hybrid run.")
    start["source_commit_at_end_full_sha"] = end["commit_sha"]
    start["source_clean_and_stable"] = bool(
        not start["tracked_source_dirty"]
        and not end["tracked_source_dirty"]
        and end["commit_sha"] == start["commit_sha"]
    )


def _max_elapsed(comm: MPI.Intracomm, started: float) -> float:
    return float(comm.allreduce(time.perf_counter() - started, op=MPI.MAX))


def _historical_peak_rss_mb() -> float | None:
    if resource is None:
        return None
    return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0


def _complex_json(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _json_default(value):
    if isinstance(value, complex):
        return _complex_json(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _h1_replicated_array_digest(values: np.ndarray) -> dict[str, Any]:
    canonical = np.ascontiguousarray(np.asarray(values, dtype="<c16"))
    return {
        "storage": "replicated-array-canonical-complex128",
        "contract": "canonical_little_endian_complex128",
        "gathered_full_vector": False,
        "rows": int(canonical.size),
        "bytes": int(canonical.nbytes),
        "sha256": hashlib.sha256(canonical.tobytes(order="C")).hexdigest(),
    }


def _h1_owned_vec_digest(vector: PETSc.Vec) -> dict[str, Any]:
    comm = vector.getComm().tompi4py()
    first, last = (int(value) for value in vector.getOwnershipRange())
    owned = np.ascontiguousarray(
        np.asarray(vector.getArray(readonly=True), dtype="<c16")
    )
    if owned.size != last - first:
        raise RuntimeError("H1 owned Vec array does not match its ownership range.")
    local_digest = hashlib.sha256()
    local_digest.update(np.asarray([first, last], dtype="<i8").tobytes())
    local_digest.update(owned.tobytes(order="C"))
    local = {
        "rank": int(comm.rank),
        "ownership_range": [first, last],
        "local_rows": int(last - first),
        "local_bytes": int(owned.nbytes),
        "sha256": local_digest.hexdigest(),
    }
    rank_digests = comm.gather(local, root=0)
    summary = None
    if comm.rank == 0:
        rank_digests = sorted(rank_digests, key=lambda item: item["rank"])
        combined = hashlib.sha256()
        for item in rank_digests:
            combined.update(
                json.dumps(item, sort_keys=True, separators=(",", ":")).encode()
            )
        summary = {
            "storage": "MPI-layout-bound-owned-local",
            "contract": "mpi_layout_bound_owned_complex128",
            "gathered_full_vector": False,
            "global_rows": int(vector.getSize()),
            "rank_digests": rank_digests,
            "sha256": combined.hexdigest(),
        }
    return comm.bcast(summary, root=0)


def _relative_vector_error(actual: PETSc.Vec, expected: PETSc.Vec) -> float:
    difference = actual.duplicate()
    try:
        actual.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), expected)
        return float(
            difference.norm()
            / max(float(actual.norm()), float(expected.norm()), 1.0e-30)
        )
    finally:
        difference.destroy()


H5_FROZEN_RANDOM_SEEDS = (3701, 3702, 3703, 3704)


def _h5_frozen_mode_selection(positive, negative) -> list[dict[str, Any]]:
    """Freeze the three H5 modal identities per propagation direction."""

    positive_modes = list(positive.modes if hasattr(positive, "modes") else positive)
    negative_modes = list(negative.modes if hasattr(negative, "modes") else negative)
    if len(positive_modes) != 120 or len(negative_modes) != 120:
        raise RuntimeError("H5 requires exactly 120 modes per direction.")

    def select_direction(direction: str, basis) -> list[dict[str, Any]]:
        modes = list(basis.modes if hasattr(basis, "modes") else basis)
        mode_count = len(modes)
        if mode_count != 120:
            raise RuntimeError("H5 requires the frozen M120 modal ordering.")
        selected: list[dict[str, Any]] = []
        used: set[int] = set()

        def append(index: int, criterion: str) -> None:
            if index in used:
                raise RuntimeError(f"H5 frozen mode identity repeats index {index}.")
            mode = modes[index]
            selected.append(
                {
                    "direction": direction,
                    "local_mode_index": int(index),
                    "global_modal_column": int(
                        index if direction == "positive" else mode_count + index
                    ),
                    "beta": _complex_json(mode.beta),
                    "kind": str(mode.kind),
                    "criterion": criterion,
                }
            )
            used.add(index)

        low_index = next(
            (
                index
                for index, mode in enumerate(modes)
                if mode.kind in {"propagating", "lossy_propagating"}
            ),
            None,
        )
        if low_index is None:
            raise RuntimeError(
                f"H5 has no finite low-index propagating mode for {direction}."
            )
        append(low_index, "lowest_propagating_or_lossy")

        evanescent_index = next(
            (
                index
                for index, mode in enumerate(modes)
                if (index not in used and index != 119 and mode.kind == "evanescent")
            ),
            None,
        )
        if evanescent_index is not None:
            append(evanescent_index, "first_kind_evanescent")
        else:
            proxy_index = next(
                (
                    index
                    for index, mode in enumerate(modes)
                    if index not in used
                    and index != 119
                    and abs(complex(mode.beta).imag) > abs(complex(mode.beta).real)
                ),
                None,
            )
            if proxy_index is None:
                raise RuntimeError(
                    f"H5 has no exact evanescent or decay-dominant proxy for {direction}."
                )
            append(proxy_index, "proxy_abs_im_beta_gt_abs_re_beta")

        append(119, "highest_retained_index")
        return selected

    return [
        *select_direction("positive", positive_modes),
        *select_direction("negative", negative_modes),
    ]


def _h5_indexed_random_values(global_ids, seed: int) -> np.ndarray:
    """Return complex SplitMix64 values indexed only by global row identity."""

    indices = np.asarray(global_ids, dtype=np.uint64)
    mask = np.uint64(0xFFFFFFFFFFFFFFFF)
    with np.errstate(over="ignore"):
        state = indices + np.uint64(int(seed))

        def splitmix(value: np.ndarray) -> np.ndarray:
            value = (value + np.uint64(0x9E3779B97F4A7C15)) & mask
            value = (value ^ (value >> np.uint64(30))) * np.uint64(
                0xBF58476D1CE4E5B9
            ) & mask
            value = (value ^ (value >> np.uint64(27))) * np.uint64(
                0x94D049BB133111EB
            ) & mask
            return value ^ (value >> np.uint64(31))

        first = splitmix(state)
        second = splitmix(state ^ np.uint64(0xD1B54A32D192ED03))
    u1 = (first >> np.uint64(11)).astype(np.float64)
    u2 = (second >> np.uint64(11)).astype(np.float64)
    u1 = (u1 + 1.0) / 9007199254740993.0
    u2 = (u2 + 1.0) / 9007199254740993.0
    radius = np.sqrt(-2.0 * np.log(u1))
    return np.asarray(
        (radius * np.cos(2.0 * np.pi * u2)) + 1j * (radius * np.sin(2.0 * np.pi * u2)),
        dtype=np.complex128,
    ) / np.sqrt(2.0)


def _h5_fill_partition_independent_random_rhs(
    vector: PETSc.Vec,
    seed: int,
) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    owned = _h5_indexed_random_values(np.arange(first, last), seed)
    if owned.size != last - first:
        raise RuntimeError("H5 random RHS ownership slice has the wrong size.")
    vector.getArray()[:] = owned
    norm = float(vector.norm())
    if not np.isfinite(norm) or norm <= 0.0:
        raise RuntimeError("H5 random RHS has a non-finite or zero global norm.")
    vector.scale(PETSc.ScalarType(1.0 / norm))


def _h5_modal_traction_rhs(
    block,
    direction: str,
    local_mode_index: int,
    scale: complex = 1.0 + 0.0j,
) -> PETSc.Vec:
    """Apply one internal modal traction column without assembling a new block."""

    if direction not in {"positive", "negative"}:
        raise ValueError("H5 modal traction direction is invalid.")
    traction_matrix = getattr(block, f"{direction}_traction")
    source = traction_matrix.createVecRight()
    result = traction_matrix.createVecLeft()
    source.set(0.0)
    first, last = (int(value) for value in source.getOwnershipRange())
    if first <= int(local_mode_index) < last:
        source.setValue(int(local_mode_index), PETSc.ScalarType(scale))
    source.assemble()
    traction_matrix.mult(source, result)
    source.destroy()
    return result


def _h5_rhs_set(
    action_system,
    block,
    selections: list[dict[str, Any]],
    *,
    side: str,
    propagation,
    random_seeds: tuple[int, ...] = H5_FROZEN_RANDOM_SEEDS,
) -> list[tuple[str, PETSc.Vec, dict[str, Any]]]:
    """Build the physical, four random, and six frozen modal RHS vectors."""

    if side not in {"bottom", "top"}:
        raise ValueError("H5 RHS side must be bottom or top.")
    specs: list[tuple[str, PETSc.Vec, dict[str, Any]]] = []
    try:
        specs.append(
            (
                "physical",
                action_system.b.copy(),
                {"kind": "physical_action_rhs", "generator": "action_system.b"},
            )
        )
        for seed in random_seeds:
            vector = action_system.A.createVecRight()
            _h5_fill_partition_independent_random_rhs(vector, seed)
            specs.append(
                (
                    f"random_seed_{seed}",
                    vector,
                    {
                        "kind": "partition_independent_complex_random",
                        "generator": "indexed_splitmix64_box_muller",
                        "seed": int(seed),
                        "normalization": "distributed_global_l2",
                    },
                )
            )
        for identity in selections:
            direction = str(identity["direction"])
            if direction not in {"positive", "negative"}:
                raise ValueError("H5 selection has an invalid direction.")
            scale = 1.0 + 0.0j
            if (side == "bottom" and direction == "negative") or (
                side == "top" and direction == "positive"
            ):
                propagation_block = (
                    propagation.forward
                    if direction == "positive"
                    else propagation.backward
                )
                scale = complex(
                    propagation_block.factors[int(identity["local_mode_index"])]
                )
            vector = _h5_modal_traction_rhs(
                block,
                direction,
                int(identity["local_mode_index"]),
                scale=scale,
            )
            specs.append(
                (
                    f"modal_{direction}_{identity['criterion']}",
                    vector,
                    {
                        "kind": "frozen_modal_traction",
                        "generator": "coupling_internal_traction_column",
                        "mode_identity": dict(identity),
                        "propagation_factor": _complex_json(scale),
                    },
                )
            )
        if len(specs) != 11:
            raise RuntimeError(f"H5 requires exactly 11 RHS, got {len(specs)}.")
        return specs
    except Exception:
        for _name, vector, _metadata in specs:
            vector.destroy()
        raise


def _h3_oracle_local_system(local_system) -> _HybridBlockLduOracleLocalSystem:
    """Extract one independent active condensed oracle and release temporaries."""

    blocks = None
    condensed = None
    port = None
    rhs = None
    try:
        blocks = extract_petsc_condensed_blocks(
            local_system.A,
            local_system.b,
            n_fe=local_system.n_fe,
            n_aux=local_system.n_external_aux,
        )
        condensed, port = build_explicit_condensed_operator(blocks)
        rhs = condensed_rhs(blocks)
        oracle = _HybridBlockLduOracleLocalSystem(
            side=local_system.side,
            local_mesh=local_system.local_mesh,
            A=condensed,
            b=rhs,
            global_size=int(local_system.n_fe),
        )
        condensed = None
        rhs = None
        return oracle
    finally:
        if port is not None:
            port.destroy()
        if blocks is not None:
            blocks.destroy()
        if condensed is not None:
            condensed.destroy()
        if rhs is not None:
            rhs.destroy()


def _h3_replicated_vec_values(vector: PETSc.Vec) -> np.ndarray:
    """Replicate a small owned auxiliary vector without gathering FE values."""

    comm = vector.getComm().tompi4py()
    owner = comm.size - 1
    values = None
    if comm.rank == owner:
        values = np.asarray(
            vector.getValues(np.arange(vector.getSize(), dtype=PETSc.IntType)),
            dtype=np.complex128,
        )
    return np.asarray(comm.bcast(values, root=owner), dtype=np.complex128)


def _global_active_column_count(matrix: PETSc.Mat) -> int:
    """Count active columns without replicating their IDs on every rank."""

    return distributed_active_column_count(matrix).global_count


def _basis_summary(basis) -> dict[str, Any]:
    identity_difference = np.asarray(
        basis.biorthogonality_matrix, dtype=np.complex128
    ) - np.eye(len(basis.modes), dtype=np.complex128)
    absolute_difference = np.abs(identity_difference)
    row_sums = np.sum(absolute_difference, axis=1)
    worst_row = int(np.argmax(row_sums))
    worst_entry = tuple(
        int(index)
        for index in np.unravel_index(
            int(np.argmax(absolute_difference)),
            absolute_difference.shape,
        )
    )
    return {
        "mode_count": len(basis.modes),
        "max_biorthogonality_identity_error": basis.max_identity_error,
        "max_biorthogonality_entry_identity_error": (basis.max_entry_identity_error),
        "biorthogonality_identity_diagnostics": {
            "worst_row_index": worst_row,
            "worst_row_sum": float(row_sums[worst_row]),
            "worst_entry_row": worst_entry[0],
            "worst_entry_column": worst_entry[1],
            "worst_entry_abs": float(absolute_difference[worst_entry]),
        },
        "left_pair_relative_errors": list(basis.left_pair_relative_errors),
        "near_degenerate_groups": [
            {
                "indices": list(group.indices),
                "beta_center_per_nm": _complex_json(group.beta_center),
                "max_relative_beta_spread": group.max_relative_beta_spread,
                "overlap_condition": group.overlap_condition,
                "normalization_method": group.normalization_method,
                "post_normalization_identity_error": (
                    group.post_normalization_identity_error
                ),
            }
            for group in basis.groups
        ],
        "betas_per_nm": [_complex_json(mode.beta) for mode in basis.modes],
        "directions": [mode.direction for mode in basis.modes],
        "kinds": [mode.kind for mode in basis.modes],
        "passive_branch_valid": [mode.passive_branch_valid for mode in basis.modes],
        "polynomial_relative_residuals": [
            mode.right.polynomial_relative_residual for mode in basis.modes
        ],
        "left_polynomial_relative_residuals": [
            mode.left_polynomial_relative_residual for mode in basis.modes
        ],
        "full_vector_gathered": basis.full_vector_gathered,
    }


def _directional_selection_summary(report) -> dict[str, Any]:
    return {
        "requested_modes": report.requested_modes,
        "candidate_modes": report.candidate_modes,
        "selected_modes": report.selected_modes,
        "desired_direction": report.desired_direction,
        "direction_counts": report.direction_counts,
        "passive_candidate_count": report.passive_candidate_count,
        "selected_candidate_indices": list(report.selected_candidate_indices),
        "flux_tolerance": report.flux_tolerance,
        "finite_candidate_count": report.finite_candidate_count,
        "numerically_infinite_candidate_count": (
            report.numerically_infinite_candidate_count
        ),
        "finite_spectrum_abs_beta_cutoff_per_nm": report.abs_beta_cutoff,
        "first_rejected_numerical_infinity_beta_per_nm": (
            None
            if report.first_rejected_numerical_infinity_beta is None
            else _complex_json(report.first_rejected_numerical_infinity_beta)
        ),
    }


class _ModalBasisCapacityStop(RuntimeError):
    """Internal control flow after writing a structured finite-spectrum negative."""


class _H5QualificationStop(RuntimeError):
    """Internal control flow after writing the H5 local qualification record."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("status", "H5 qualification complete"))
        self.record = record


NUMERICAL_INFINITY_BETA_H_CUTOFF = 1.0e4


def _case080_reference_path(
    degree: int,
    h_nm: float,
    reference_by_degree_and_h: dict[tuple[int, float], Path] | None = None,
) -> Path | None:
    references = (
        REFERENCE_BY_DEGREE_AND_H
        if reference_by_degree_and_h is None
        else reference_by_degree_and_h
    )
    matches = [
        path
        for (reference_degree, level), path in references.items()
        if degree == reference_degree and abs(h_nm - level) <= 1.0e-12
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple Case080 references match degree={degree}, h={h_nm} nm."
        )
    return matches[0] if matches else None


def _serialize_reference_path(path: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _normalize_full3d_reference_record(
    reference: dict[str, Any],
    *,
    path: Path,
) -> dict[str, Any]:
    """Normalize a native watchdog record without writing a derived descriptor."""

    if reference.get("record_type") == "task034_full3d_reference":
        return reference
    if reference.get("schema_version") != "task033.full3d-watchdog.v1":
        return reference
    try:
        source = reference["source"]
        qualification = reference["qualification"]
        solver = reference["solver_summary"]
        resource_authority = reference["resource_authority"]
        archive = Path(str(solver["full3d_reference_archive"]))
        metadata = Path(str(solver["full3d_reference_metadata"]))
        if not archive.is_absolute():
            archive = ROOT / archive
        if not metadata.is_absolute():
            metadata = ROOT / metadata
        archive = archive.resolve()
        metadata = metadata.resolve()
        run_root = _serialize_reference_path(archive.parent)
        commit_sha = str(source["commit_sha"]).lower()
        polarization_kind = str(solver["polarization_kind"]).lower()
        archive_sha256 = str(solver["full3d_reference_archive_sha256"]).lower()
        finite_results = (
            solver["linear_system_relative_residual"],
            solver["R_total"],
            solver["T_total"],
            solver["A_balance"],
            solver["A_volume_total"],
            solver["energy_closure_error_port_volume"],
            resource_authority["memory_authority_gib"],
        )
        raw_valid = bool(
            reference["status"] == "full3d_reference_pass"
            and reference["run_kind"] == "full-solve"
            and qualification["pass"] is True
            and reference["no_swap"] is True
            and source["tracked_source_dirty"] is False
            and source["stable_and_clean_after"] is True
            and solver["case_status"] == "completed"
            and solver["official_result"] is True
            and solver["full3d_reference_exported"] is True
            and polarization_kind in {"s", "p"}
            and math.isclose(float(solver["incident_theta_deg"]), 80.0)
            and math.isclose(float(solver["incident_phi_deg"]), 0.0)
            and float(solver["linear_system_relative_residual"]) <= 1.0e-9
            and archive.name == "full3d_reference_samples.npz"
            and metadata.name == "full3d_reference_samples.json"
            and metadata.parent == archive.parent
            and len(commit_sha) == 40
            and all(character in "0123456789abcdef" for character in commit_sha)
            and len(archive_sha256) == 64
            and all(character in "0123456789abcdef" for character in archive_sha256)
            and all(np.isfinite(float(value)) for value in finite_results)
        )
    except (KeyError, TypeError, ValueError, OSError) as error:
        raise RuntimeError(
            f"Native full3D watchdog reference is incomplete: {path}"
        ) from error
    if not raw_valid:
        raise RuntimeError(
            f"Native full3D watchdog reference failed its raw Gate: {path}"
        )
    return {
        "record_type": "task034_full3d_reference",
        "metadata": {
            "commit_sha": commit_sha,
            "git_dirty": False,
            "tracked_source_dirty": False,
            "host_environment_id": "WSL2-Ubuntu-24.04",
            "provenance": (
                "in-memory normalization of native full3D watchdog evidence"
            ),
        },
        "physical_model": {
            "wavelength_nm": 13.5,
            "incident_theta_deg": 80.0,
            "incident_grazing_deg": 10.0,
            "incident_phi_deg": 0.0,
            "polarization_kind": polarization_kind,
            "nedelec_degree": int(reference["degree"]),
            "mesh_h_nm": float(reference["h_nm"]),
            "mpi_size": int(reference["mpi_size"]),
            "linear_solver": "direct_lu_mumps",
        },
        "results": {
            "case_status": solver["case_status"],
            "official_result": True,
            "linear_system_true_relative_residual": float(
                solver["linear_system_relative_residual"]
            ),
            "R_total": float(solver["R_total"]),
            "T_total": float(solver["T_total"]),
            "A_balance": float(solver["A_balance"]),
            "A_volume_total": float(solver["A_volume_total"]),
            "energy_closure_error_port_volume": float(
                solver["energy_closure_error_port_volume"]
            ),
            "external_memory_authority_gib": float(
                resource_authority["memory_authority_gib"]
            ),
        },
        "artifacts": {
            "ignored_run_root": run_root,
            "reference_npz_sha256": archive_sha256,
        },
        "qualification": {
            "phase1_reference_pass": True,
            "grid_converged": False,
            "no_swap": True,
            "watchdog_status": reference["status"],
            "heavy_artifacts_tracked": False,
        },
    }


def _validate_case080_reference_identity(
    reference: dict[str, Any],
    *,
    degree: int,
    h_nm: float,
    path: Path,
    polarization_kind: str = "s",
) -> None:
    try:
        physical_model = reference["physical_model"]
        qualification = reference["qualification"]
        metadata = reference["metadata"]
        commit_sha = str(metadata["commit_sha"]).lower()
        identity_valid = (
            physical_model["nedelec_degree"] == degree
            and abs(float(physical_model["mesh_h_nm"]) - h_nm) <= 1.0e-12
            and abs(float(physical_model["incident_grazing_deg"]) - 10.0) <= 1.0e-12
            and abs(float(physical_model["incident_theta_deg"]) - 80.0) <= 1.0e-12
            and abs(float(physical_model["incident_phi_deg"])) <= 1.0e-12
            and physical_model["polarization_kind"] == polarization_kind
            and abs(float(physical_model["wavelength_nm"]) - 13.5) <= 1.0e-12
            and qualification["phase1_reference_pass"] is True
            and metadata["git_dirty"] is False
            and metadata["tracked_source_dirty"] is False
            and len(commit_sha) == 40
            and all(character in "0123456789abcdef" for character in commit_sha)
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            f"Case080 reference identity is incomplete or invalid: {path}"
        ) from error
    if not identity_valid:
        raise RuntimeError(
            "Case080 reference identity does not match the requested p/h and "
            f"pinned 10-degree {polarization_kind}-polarized 13.5-nm model: {path}"
        )


def _load_case080_reference(
    degree: int,
    h_nm: float,
    reference_by_degree_and_h: dict[tuple[int, float], Path] | None = None,
    *,
    polarization_kind: str = "s",
) -> tuple[Path, dict[str, Any]] | None:
    reference_path = _case080_reference_path(degree, h_nm, reference_by_degree_and_h)
    if reference_path is None:
        return None
    if not reference_path.exists():
        raise FileNotFoundError(
            f"Pinned Case080 reference record is missing: {reference_path}"
        )
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(
            f"Cannot load pinned Case080 reference record: {reference_path}"
        ) from error
    reference = _normalize_full3d_reference_record(reference, path=reference_path)
    _validate_case080_reference_identity(
        reference,
        degree=degree,
        h_nm=h_nm,
        path=reference_path,
        polarization_kind=polarization_kind,
    )
    return reference_path, reference


def _reference_comparison(
    loaded_reference: tuple[Path, dict[str, Any]] | None,
    port_power: dict[str, Any],
) -> dict[str, Any] | None:
    if loaded_reference is None:
        return None
    reference_path, reference = loaded_reference
    results = reference["results"]
    return {
        "reference_file": _serialize_reference_path(reference_path),
        "reference_commit_sha": reference["metadata"]["commit_sha"],
        "reference_grid_converged": reference["qualification"]["grid_converged"],
        "hybrid_minus_full3d": {
            "R_total": float(port_power["R_total"] - results["R_total"]),
            "T_total": float(port_power["T_total"] - results["T_total"]),
            "A_balance": float(port_power["A_balance"] - results["A_balance"]),
        },
        "full3d": {
            "R_total": results["R_total"],
            "T_total": results["T_total"],
            "A_balance": results["A_balance"],
            "A_volume_total": results["A_volume_total"],
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reference_archive(
    loaded_reference: tuple[Path, dict[str, Any]] | None,
) -> tuple[Path, Path, dict[str, Any]] | None:
    if loaded_reference is None:
        return None
    record_path, record = loaded_reference
    run_root = Path(record["artifacts"]["ignored_run_root"])
    if not run_root.is_absolute():
        run_root = ROOT / run_root
    archive = run_root / "full3d_reference_samples.npz"
    if not archive.exists():
        raise FileNotFoundError(
            f"Pinned full-3D selected-plane archive is missing: {archive}"
        )
    expected_sha = str(record["artifacts"]["reference_npz_sha256"])
    actual_sha = _sha256(archive)
    if actual_sha != expected_sha:
        raise RuntimeError(
            f"Full-3D selected-plane archive SHA256 {actual_sha} != {expected_sha}."
        )
    return archive, record_path, record


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Task32 Phase6 real-QEP hybrid augmented direct diagnostic"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--h-nm", type=float, default=5.0)
    parser.add_argument("--degree", type=int, choices=(1, 2, 3, 4, 6), default=2)
    parser.add_argument(
        "--modal-h-nm",
        type=float,
        help=(
            "Optional independent cross-section QEP mesh size. The local 3D "
            "FEM mesh remains controlled by --h-nm."
        ),
    )
    parser.add_argument(
        "--modal-degree",
        type=int,
        choices=(1, 2, 3, 4, 6),
        help=(
            "Optional independent cross-section QEP polynomial degree. The "
            "local 3D FEM degree remains controlled by --degree."
        ),
    )
    parser.add_argument(
        "--internal-propagation-model",
        choices=("continuous_beta", "full3d_uniform_cg"),
        default="continuous_beta",
        help=(
            "Axial propagation used between the two Hybrid interfaces. "
            "full3d_uniform_cg is an explicit same-p/h Full3D closure audit "
            "qualified only for a fixed rectangular, axis-aligned affine "
            "tensor-hexa mesh with uniform middle-region z spacing, one "
            "axial h, p1-p6, complex128, Floquet and sparse auxiliary DtN; "
            "nonuniform/local-h/curved/mixed meshes fail closed. "
            "continuous_beta remains the ordinary default."
        ),
    )
    parser.add_argument(
        "--internal-traction-model",
        choices=(
            "continuous_qep_beta",
            "scalar_cg_discrete_derivative",
        ),
        default="continuous_qep_beta",
        help=(
            "Modal interface traction symbol. The scalar-CG derivative is an "
            "explicit diagnostic and requires full3d_uniform_cg propagation "
            "under the same uniform-z affine-hexa qualification scope; "
            "unsupported meshes fail closed without fallback. "
            "continuous_qep_beta remains the ordinary default."
        ),
    )
    parser.add_argument(
        "--stage4-full3d-assembly-backend",
        choices=(
            STANDARD_FULL_ASSEMBLY_BACKEND,
            ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND,
        ),
        default=STANDARD_FULL_ASSEMBLY_BACKEND,
        help=(
            "Single public local-FE assembly port. Static condensation is "
            "explicit opt-in; standard_full remains the ordinary default."
        ),
    )
    parser.add_argument(
        "--full3d-reference",
        type=Path,
        help=(
            "Optional explicit same-p/h full3D descriptor. This is required "
            "for review-v5 coarse p3 candidates that are not in the legacy "
            "reference registry."
        ),
    )
    parser.add_argument("--full3d-reference-sha256")
    parser.add_argument(
        "--task035c-p6-h10-gate",
        action="store_true",
        help=(
            "Explicitly open only the fixed-rectangular Task035c p6/h10 "
            "M120/M160 Hybrid path. Ordinary defaults remain unchanged."
        ),
    )
    parser.add_argument(
        "--task037b-h1-gate",
        action="store_true",
        help="Open only the frozen Task037b H1 augmented MPI8 path.",
    )
    parser.add_argument(
        "--task037b-h3-gate",
        action="store_true",
        help="Open only the frozen Task037b H3 exact block-LDU MPI8 path.",
    )
    parser.add_argument(
        "--task037b-h4-gate",
        action="store_true",
        help="Open only the frozen Task037b H4 bounded modal-block diagnostic path.",
    )
    parser.add_argument(
        "--task037b-h5-gate",
        action="store_true",
        help="Open only the frozen Task037b H5 local-inverse qualification path.",
    )
    parser.add_argument("--task035c-p6-preflight-authority", type=Path)
    parser.add_argument("--task035c-p6-preflight-sha256")
    parser.add_argument("--bottom-interface-nm", type=float, default=10.0)
    parser.add_argument("--top-interface-nm", type=float, default=110.0)
    parser.add_argument("--graded-reference-h", type=float, choices=(5.0, 3.0))
    parser.add_argument("--graded-coarse-factor", type=float, default=2.0)
    parser.add_argument(
        "--graded-profile",
        choices=("mechanism", "conservative", "balanced", "aggressive"),
        default="mechanism",
    )
    parser.add_argument("--incident-grazing-deg", type=float, default=10.0)
    parser.add_argument(
        "--polarization-kind",
        choices=("s", "p"),
        default="s",
    )
    parser.add_argument("--requested-modes", type=int, default=2)
    parser.add_argument(
        "--candidate-modes",
        type=int,
        help=(
            "QEP candidate count per target branch before passive-direction filtering. "
            "Default keeps M for M<=6 and uses 2M for wider funnels."
        ),
    )
    parser.add_argument("--near-degenerate-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--block-rotation-tolerance", type=float, default=1.0e-6)
    parser.add_argument("--verified-clean-sha")
    parser.add_argument("--allow-dirty-research", action="store_true")
    parser.add_argument(
        "--memory-stages",
        type=Path,
        help="Optional JSONL stage marker consumed by the external memory sampler.",
    )
    parser.add_argument(
        "--compare-modal-schur",
        action="store_true",
        help="Also build the Phase7 multi-RHS modal-Schur direct path and compare it with augmented.",
    )
    parser.add_argument(
        "--comparison-solver-path",
        choices=("fast", "minimal"),
        default="fast",
        help=(
            "Modal-Schur builder used by --compare-modal-schur. The fast default "
            "preserves Task32 behavior; Task33 formal comparisons use minimal."
        ),
    )
    parser.add_argument(
        "--solver-path",
        choices=(
            "augmented",
            "modal-schur-fast",
            "modal-schur-memory-minimal",
            "block-ldu-exact",
            "local-inverse-qualification",
        ),
        default="augmented",
        help=(
            "Primary direct solve lifecycle. Non-augmented choices are standalone "
            "Phase10 memory paths and never retain the monolithic augmented factor."
        ),
    )
    parser.add_argument("--container-image", default="myfenics-stage4:task28")
    parser.add_argument(
        "--container-digest",
        default=(
            "sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d"
        ),
    )
    parser.add_argument(
        "--host-environment-id",
        default=os.environ.get("TASK032_HOST_ENVIRONMENT_ID", "SK-20260601OSDE"),
    )
    args = parser.parse_args(argv)
    selected_scoped_gates = (
        args.task035c_p6_h10_gate,
        args.task037b_h1_gate,
        args.task037b_h3_gate,
        args.task037b_h4_gate,
        args.task037b_h5_gate,
    )
    if sum(bool(value) for value in selected_scoped_gates) > 1:
        parser.error(
            "Task035c p6/h10, Task037b H1, H3, H4, and H5 gates are "
            "mutually exclusive."
        )
    if (
        args.solver_path == "local-inverse-qualification"
        and not args.task037b_h5_gate
    ):
        parser.error(
            "local-inverse-qualification requires --task037b-h5-gate."
        )
    if args.degree == 6 and not any(selected_scoped_gates):
        parser.error(
            "p6 is fail-closed; pass a fixed scoped Task035c, Task037b H1, "
            "or Task037b H3/H4/H5 gate."
        )
    if args.task035c_p6_h10_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes in TASK035C_P6_H10_MODE_COUNTS
            and args.candidate_modes == 2 * args.requested_modes
            and args.solver_path == "modal-schur-memory-minimal"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend in TASK035C_P6_H10_BACKENDS
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and not args.allow_dirty_research
        )
        if not scoped:
            parser.error(
                "--task035c-p6-h10-gate is restricted to clean-source fixed "
                "rectangular p6/h10 S-polarized Hybrid M120/M160, explicit "
                "modal p6/h10, exact 2M pool, modal-schur-memory-minimal, "
                "the qualified discrete axial propagation/traction pair, "
                "10/110 nm interfaces, standard/static backend, and "
                "hash-bound historical and matching Full3D authorities."
            )
    elif args.task037b_h1_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "augmented"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend
            == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
            and not args.allow_dirty_research
        )
        if not scoped:
            parser.error(
                "--task037b-h1-gate is restricted to the fixed p6/h10, "
                "10/110 nm, S-polarized, full3d/scalar-CG, M120+M120, "
                "candidate240, augmented, static-condensed MPI8 path."
            )
    elif args.task037b_h3_gate or args.task037b_h4_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "block-ldu-exact"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend
            == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
            and not args.allow_dirty_research
        )
        if not scoped:
            parser.error(
                "--task037b-h3-gate/--task037b-h4-gate is restricted to the fixed WSL p6/h10, "
                "10/110 nm, S-polarized, full3d/scalar-CG, M120+M120, "
                "candidate240, block-ldu-exact, static-condensed MPI8 path."
            )
    elif args.task037b_h5_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "local-inverse-qualification"
            and args.comparison_solver_path == "fast"
            and not args.compare_modal_schur
            and args.stage4_full3d_assembly_backend
            == ASSEMBLY_TIME_STATIC_CONDENSED_BACKEND
            and math.isclose(args.bottom_interface_nm, 10.0)
            and math.isclose(args.top_interface_nm, 110.0)
            and args.graded_reference_h is None
            and math.isclose(args.incident_grazing_deg, 10.0)
            and args.polarization_kind == "s"
            and args.internal_propagation_model == "full3d_uniform_cg"
            and args.internal_traction_model == "scalar_cg_discrete_derivative"
            and args.full3d_reference is not None
            and valid_hex_digest(args.full3d_reference_sha256, 64)
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.host_environment_id == "WSL2-Ubuntu-24.04"
            and not args.allow_dirty_research
        )
        if not scoped:
            parser.error(
                "--task037b-h5-gate is restricted to the fixed WSL p6/h10, "
                "10/110 nm, S-polarized, full3d/scalar-CG, M120+M120, "
                "candidate240, local-inverse-qualification, "
                "static-condensed MPI8 path."
            )
    elif (
        args.task035c_p6_preflight_authority is not None
        or args.task035c_p6_preflight_sha256 is not None
        or args.full3d_reference_sha256 is not None
    ):
        parser.error("Task035c/H1/H3/H4/H5 authority SHA arguments require a scoped gate.")
    return args


def _task035c_worker_authority_gate(
    args: argparse.Namespace,
    *,
    current_source_sha: str | None,
    mpi_size: int,
) -> dict[str, Any] | None:
    if not (
        args.task035c_p6_h10_gate
        or args.task037b_h1_gate
        or args.task037b_h3_gate
        or args.task037b_h4_gate
        or args.task037b_h5_gate
    ):
        return None

    authority_path = args.task035c_p6_preflight_authority
    reference_path = args.full3d_reference
    if authority_path is None or reference_path is None:
        raise SystemExit("Task035c/H1 authority paths are required.")
    authority_path = (
        authority_path if authority_path.is_absolute() else ROOT / authority_path
    ).resolve()
    reference_path = (
        reference_path if reference_path.is_absolute() else ROOT / reference_path
    ).resolve()
    try:
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035c p6/h10 historical authority is unreadable: {exc}"
        ) from exc
    try:
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035c p6/h10 Full3D reference is unreadable: {exc}"
        ) from exc
    try:
        authority_relative = authority_path.relative_to(ROOT).as_posix()
    except ValueError:
        authority_relative = None
    authority_is_tracked = bool(
        authority_relative is not None
        and _git("ls-files", "--error-unmatch", "--", authority_relative) is not None
    )
    preflight_gate = task035c_p6_h10_preflight_authority_gate(
        authority if isinstance(authority, dict) else None,
        expected_sha256=args.task035c_p6_preflight_sha256,
        observed_sha256=_sha256(authority_path),
        authority_is_tracked=authority_is_tracked,
    )
    reference_gate = (
        task037b_h1_pinned_full3d_reference_gate(
            reference if isinstance(reference, dict) else None,
            expected_sha256=args.full3d_reference_sha256,
            observed_sha256=_sha256(reference_path),
            current_source_sha=current_source_sha,
            assembly_backend=args.stage4_full3d_assembly_backend,
            mpi_size=mpi_size,
        )
        if (
            args.task037b_h1_gate
            or args.task037b_h3_gate
            or args.task037b_h4_gate
            or args.task037b_h5_gate
        )
        else task035c_p6_h10_full3d_reference_gate(
            reference if isinstance(reference, dict) else None,
            expected_sha256=args.full3d_reference_sha256,
            observed_sha256=_sha256(reference_path),
            current_source_sha=current_source_sha,
            assembly_backend=args.stage4_full3d_assembly_backend,
            mpi_size=mpi_size,
        )
    )
    gate = {
        "schema_version": (
            "task037b.h4-worker-authority-gate.v1"
            if args.task037b_h4_gate
            else "task037b.h3-worker-authority-gate.v1"
            if args.task037b_h3_gate
            else "task037b.h5-worker-authority-gate.v1"
            if args.task037b_h5_gate
            else "task035c.p6-h10-worker-authority-gate.v1"
        ),
        "pass": bool(preflight_gate["pass"] and reference_gate["pass"]),
        "historical_preflight": {
            **preflight_gate,
            "path": str(authority_path),
        },
        "matching_full3d_reference": {
            **reference_gate,
            "path": str(reference_path),
        },
    }
    gate["failures"] = [
        *(
            []
            if preflight_gate["pass"]
            else [
                f"historical_preflight:{failure}"
                for failure in preflight_gate["failures"]
            ]
        ),
        *(
            []
            if reference_gate["pass"]
            else [
                f"matching_full3d_reference:{failure}"
                for failure in reference_gate["failures"]
            ]
        ),
    ]
    if not gate["pass"]:
        raise SystemExit(f"Task035c p6/h10 worker authority failed: {gate['failures']}")
    return gate


def _h5_true_relative_residual(
    operator: PETSc.Mat,
    rhs: PETSc.Vec,
    solution: PETSc.Vec,
) -> float:
    residual = rhs.duplicate()
    try:
        operator.mult(solution, residual)
        residual.scale(PETSc.ScalarType(-1.0))
        residual.axpy(PETSc.ScalarType(1.0), rhs)
        return float(residual.norm()) / max(float(rhs.norm()), 1.0e-30)
    finally:
        residual.destroy()


def _run_h5_local_qualification(
    *,
    args: argparse.Namespace,
    comm: MPI.Intracomm,
    provenance: dict[str, Any],
    authority_gate: dict[str, Any] | None,
    cfg: Any,
    positive: Any,
    negative: Any,
    bottom: Any,
    top: Any,
    coupling: Any,
    oracle_bottom: _HybridBlockLduOracleLocalSystem,
    oracle_top: _HybridBlockLduOracleLocalSystem,
    timings: dict[str, float],
    total_started: float,
    mark_stage,
    progress,
) -> None:
    """Run the bounded H5a/H5b local qualification and raise its stop record."""

    selections = _h5_frozen_mode_selection(positive, negative)
    propagation = coupling.propagation
    rhs_sets = {
        "bottom": _h5_rhs_set(
            bottom,
            coupling.bottom,
            selections,
            side="bottom",
            propagation=propagation,
        ),
        "top": _h5_rhs_set(
            top,
            coupling.top,
            selections,
            side="top",
            propagation=propagation,
        ),
    }
    direct_references: dict[str, dict[str, PETSc.Vec]] = {
        "bottom": {},
        "top": {},
    }
    bottom_inverse = None
    top_inverse = None
    h5a_sides: dict[str, Any] = {}
    h5b_sides: dict[str, Any] = {}
    h5a_pass = True
    h5b_pass = False

    rhs_manifest: dict[str, list[dict[str, Any]]] = {"bottom": [], "top": []}
    for side, rhs_list in rhs_sets.items():
        for name, vector, metadata in rhs_list:
            rhs_manifest[side].append(
                {
                    "name": name,
                    "metadata": metadata,
                    "digest": _h1_owned_vec_digest(vector),
                }
            )

    try:
        for side, oracle, action, rhs_list in (
            ("bottom", oracle_bottom, bottom, rhs_sets["bottom"]),
            ("top", oracle_top, top, rhs_sets["top"]),
        ):
            factor = None
            side_record: dict[str, Any] = {
                "rhs": [],
                "factor_before": None,
                "factor_after": None,
            }
            mark_stage(f"h5a_{side}_factor")
            factor_started = time.perf_counter()
            try:
                factor, factor_setup = _factor_local(oracle.A)
                side_record["factor_setup_seconds"] = float(factor_setup)
                side_record["factor_before"] = {
                    "factor_count": 1,
                    "inventory": _local_factor_inventory(factor),
                }
                timings[f"h5a_{side}_factor"] = _max_elapsed(
                    comm, factor_started
                )
                mark_stage(f"h5a_{side}_solve")
                solve_started = time.perf_counter()
                for name, rhs, metadata in rhs_list:
                    candidate = rhs.duplicate()
                    try:
                        factor.solve(rhs, candidate)
                        direct_residual = _h5_true_relative_residual(
                            oracle.A, rhs, candidate
                        )
                        action_residual = _h5_true_relative_residual(
                            action.A, rhs, candidate
                        )
                        reason = int(factor.getConvergedReason())
                        iterations = int(factor.getIterationNumber())
                        solution_digest = _h1_owned_vec_digest(candidate)
                        direct_references[side][name] = candidate
                        candidate = None
                        row = {
                            "name": name,
                            "metadata": metadata,
                            "converged_reason": reason,
                            "iterations": iterations,
                            "explicit_oracle_true_residual": float(direct_residual),
                            "matrix_free_action_true_residual": float(action_residual),
                            "solution_digest": solution_digest,
                            "pass": bool(
                                reason > 0
                                and np.isfinite(direct_residual)
                                and np.isfinite(action_residual)
                                and direct_residual <= 1.0e-10
                                and action_residual <= 1.0e-10
                            ),
                        }
                        side_record["rhs"].append(row)
                        progress(
                            f"Task37b H5a {side}/{name}: reason={reason} "
                            f"iterations={iterations} "
                            f"direct_true={direct_residual:.6e} "
                            f"action_true={action_residual:.6e}"
                        )
                    finally:
                        if candidate is not None:
                            candidate.destroy()
                side_record["solve_seconds"] = _max_elapsed(
                    comm, solve_started
                )
                timings[f"h5a_{side}_solve"] = side_record["solve_seconds"]
            finally:
                release_started = time.perf_counter()
                if factor is not None:
                    factor.destroy()
            mark_stage(f"h5a_{side}_release")
            side_record["factor_after"] = {
                "factor_count": 0,
                "released": True,
            }
            timings[f"h5a_{side}_release"] = _max_elapsed(
                comm, release_started
            )
            side_record["pass"] = bool(
                side_record["rhs"]
                and all(row["pass"] for row in side_record["rhs"])
            )
            h5a_sides[side] = side_record
            h5a_pass = bool(h5a_pass and side_record["pass"])

        oracle_bottom.destroy()
        oracle_top.destroy()
        comm.barrier()
        heap_trim_started = time.perf_counter()
        mark_stage("h5_post_direct_heap_trim")
        trim_local = _trim_process_heap()
        trim_ranks = comm.allgather(trim_local)
        comm.barrier()
        timings["h5_post_direct_heap_trim"] = _max_elapsed(
            comm, heap_trim_started
        )
        oracle_release = {
            "bottom_A_b_destroyed": True,
            "top_A_b_destroyed": True,
            "heap_trim_by_rank": trim_ranks,
        }

        h5b_factor_count_before = None
        h5b_bottom_release_factor_count = None
        h5b_top_release_factor_count = None
        h5b_disposition = "not_run_due_h5a_failure"
        if h5a_pass:
            h5b_disposition = "completed"
            mark_stage("h5b_simultaneous_inverse_setup")
            setup_started = time.perf_counter()
            bottom_inverse = build_hybrid_local_iterative_inverse(bottom)
            top_inverse = build_hybrid_local_iterative_inverse(top)
            timings["h5b_simultaneous_inverse_setup"] = _max_elapsed(
                comm, setup_started
            )
            inverse_by_side = {"bottom": bottom_inverse, "top": top_inverse}
            for side, inverse in inverse_by_side.items():
                h5b_sides[side] = {
                    "configuration": inverse._diagnostics(),
                    "rhs": [],
                    "factor_count_before": int(
                        inverse.smoother.diagnostics["global_subdomain_count"]
                    ),
                }
            h5b_factor_count_before = sum(
                h5b_sides[side]["factor_count_before"]
                for side in ("bottom", "top")
            )

            for side, stage, inverse in (
                ("bottom", "h5b_bottom_solves", bottom_inverse),
                ("top", "h5b_top_solves", top_inverse),
            ):
                mark_stage(stage)
                solve_started = time.perf_counter()
                for name, rhs, metadata in rhs_sets[side]:
                    first = None
                    second = None
                    try:
                        first = inverse.solve(rhs)
                        second = inverse.solve(rhs)
                        direct = direct_references[side][name]
                        repeat_error = _relative_vector_error(
                            second.solution, first.solution
                        )
                        first_direct_error = _relative_vector_error(
                            first.solution, direct
                        )
                        second_direct_error = _relative_vector_error(
                            second.solution, direct
                        )
                        stationary_keys = {1, 2, 4, 8}
                        first_stationary = first.stationary_correction_residuals
                        second_stationary = second.stationary_correction_residuals
                        row = {
                            "name": name,
                            "metadata": metadata,
                            "first": {
                                "converged_reason": int(first.converged_reason),
                                "iterations": int(first.iterations),
                                "reported_relative_residual": float(
                                    first.reported_relative_residual
                                ),
                                "true_relative_residual": float(
                                    first.true_relative_residual
                                ),
                                "setup_seconds": float(first.setup_seconds),
                                "solve_seconds": float(first.solve_seconds),
                                "apply_seconds": float(first.apply_seconds),
                                "solution_digest": _h1_owned_vec_digest(
                                    first.solution
                                ),
                                "direct_solution_relative_error": float(
                                    first_direct_error
                                ),
                                "stationary_correction_residuals": (
                                    first.stationary_correction_residuals
                                ),
                            },
                            "second": {
                                "converged_reason": int(second.converged_reason),
                                "iterations": int(second.iterations),
                                "reported_relative_residual": float(
                                    second.reported_relative_residual
                                ),
                                "true_relative_residual": float(
                                    second.true_relative_residual
                                ),
                                "setup_seconds": float(second.setup_seconds),
                                "solve_seconds": float(second.solve_seconds),
                                "apply_seconds": float(second.apply_seconds),
                                "solution_digest": _h1_owned_vec_digest(
                                    second.solution
                                ),
                                "direct_solution_relative_error": float(
                                    second_direct_error
                                ),
                                "stationary_correction_residuals": (
                                    second.stationary_correction_residuals
                                ),
                            },
                            "repeat_solution_relative_error": float(repeat_error),
                            "pass": bool(
                                first.converged_reason > 0
                                and second.converged_reason > 0
                                and first.iterations <= 300
                                and second.iterations <= 300
                                and first.converged_reason
                                == second.converged_reason
                                and first.iterations == second.iterations
                                and np.isfinite(first.reported_relative_residual)
                                and np.isfinite(second.reported_relative_residual)
                                and np.isfinite(first.true_relative_residual)
                                and np.isfinite(second.true_relative_residual)
                                and np.isfinite(first.setup_seconds)
                                and np.isfinite(first.solve_seconds)
                                and np.isfinite(first.apply_seconds)
                                and np.isfinite(second.setup_seconds)
                                and np.isfinite(second.solve_seconds)
                                and np.isfinite(second.apply_seconds)
                                and first.true_relative_residual <= 1.0e-8
                                and second.true_relative_residual <= 1.0e-8
                                and np.isfinite(repeat_error)
                                and repeat_error <= 1.0e-10
                                and np.isfinite(first_direct_error)
                                and np.isfinite(second_direct_error)
                                and set(first_stationary) == stationary_keys
                                and set(second_stationary) == stationary_keys
                                and all(
                                    np.isfinite(value)
                                    for value in first_stationary.values()
                                )
                                and all(
                                    np.isfinite(value)
                                    for value in second_stationary.values()
                                )
                                and first.diagnostics["no_direct_fallback"] is True
                                and second.diagnostics["no_direct_fallback"] is True
                            ),
                        }
                        h5b_sides[side]["rhs"].append(row)
                        progress(
                            f"Task37b H5b {side}/{name}: "
                            f"first_reason={first.converged_reason} "
                            f"first_iterations={first.iterations} "
                            f"first_true={first.true_relative_residual:.6e} "
                            f"second_reason={second.converged_reason} "
                            f"second_iterations={second.iterations} "
                            f"second_true={second.true_relative_residual:.6e}"
                        )
                    finally:
                        if first is not None:
                            first.destroy()
                        if second is not None:
                            second.destroy()
                h5b_sides[side]["solve_seconds"] = _max_elapsed(
                    comm, solve_started
                )
                timings[stage] = h5b_sides[side]["solve_seconds"]

            h5b_pass = bool(
                all(
                    h5b_sides[side]["rhs"]
                    and all(row["pass"] for row in h5b_sides[side]["rhs"])
                    for side in ("bottom", "top")
                )
            )

        h5_no_direct_fallback: bool | str = "not_run"
        if h5a_pass:
            h5_no_direct_fallback = bool(
                all(
                    h5b_sides[side]["configuration"]["no_direct_fallback"]
                    is True
                    for side in ("bottom", "top")
                )
            )

        release_started = time.perf_counter()
        mark_stage("h5b_release_record")
        if bottom_inverse is not None:
            bottom_inverse.destroy()
            bottom_inverse = None
            h5b_bottom_release_factor_count = int(
                h5b_sides["top"]["factor_count_before"]
            )
            h5b_sides["bottom"]["factor_count_after_destroy"] = 0
            h5b_sides["bottom"]["factors_released"] = True
            h5b_sides["bottom"]["remaining_factor_count"] = (
                h5b_bottom_release_factor_count
            )
        bottom_after_release: bool | str = "not_run"
        if h5a_pass:
            bottom_after_release = bool(
                bottom.A.getType() == "python" and top.A.getType() == "python"
            )
        if top_inverse is not None:
            top_inverse.destroy()
            top_inverse = None
            h5b_top_release_factor_count = 0
            h5b_sides["top"]["factor_count_after_destroy"] = 0
            h5b_sides["top"]["factors_released"] = True
            h5b_sides["top"]["remaining_factor_count"] = 0
        action_survives: bool | str = "not_run"
        if h5a_pass:
            action_survives = bool(
                bottom.A.getType() == "python" and top.A.getType() == "python"
            )
        timings["h5b_release_record"] = _max_elapsed(
            comm, release_started
        )

        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        h5_pass = bool(h5a_pass and h5b_pass)
        h5_telemetry = {
            "task037b_h5_gate": True,
            "frozen_modes": selections,
            "rhs_manifest": rhs_manifest,
            "h5a": {
                "all_pass": h5a_pass,
                "sides": h5a_sides,
                "oracle_release": oracle_release,
            },
            "h5b": {
                "all_pass": h5b_pass,
                "disposition": h5b_disposition,
                "sides": h5b_sides,
                "simultaneous_factor_count_before": (
                    h5b_factor_count_before
                    if h5b_factor_count_before is not None
                    else "not_run"
                ),
                "bottom_release_factor_count": (
                    h5b_bottom_release_factor_count
                    if h5b_bottom_release_factor_count is not None
                    else "not_run"
                ),
                "top_release_factor_count": (
                    h5b_top_release_factor_count
                    if h5b_top_release_factor_count is not None
                    else "not_run"
                ),
                "action_survives_after_bottom_release": bottom_after_release,
                "action_survives_after_release": action_survives,
            },
            "operator_inventory": {
                "bottom": dict(bottom.inventory),
                "top": dict(top.inventory),
                "global_block_action_constructed": False,
                "global_A_materialized": False,
                "external_C_D_materialized": False,
            },
            "timings": {
                key: timings[key]
                for key in (
                    "h5_action_coupling_build",
                    "h5a_bottom_factor",
                    "h5a_bottom_solve",
                    "h5a_bottom_release",
                    "h5a_top_factor",
                    "h5a_top_solve",
                    "h5a_top_release",
                    "h5_post_direct_heap_trim",
                    "h5b_simultaneous_inverse_setup",
                    "h5b_bottom_solves",
                    "h5b_top_solves",
                    "h5b_release_record",
                )
                if key in timings
            },
            "swap_status": "not_evaluated_external_watchdog",
            "official_physics": {
                "R": "not_run",
                "T": "not_run",
                "A": "not_run",
                "A_volume": "not_run",
                "field_reconstruction": "not_run",
            },
        }
        record = {
            "schema_version": 1,
            "record_schema": "task037b.h5-local-inverse-qualification.v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "benchmark_id": "task037b_h5_local_inverse_qualification",
            "status": (
                "task037b_h5_worker_gate_pass"
                if h5_pass
                else "task037b_h5_worker_gate_failed"
            ),
            "metadata": {
                **provenance,
                "command": "python -m benchmarks.run_task032_phase6_augmented "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": int(comm.size),
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "task035c_p6_h10_authority_gate": authority_gate,
            },
            "case": {
                "degree": int(args.degree),
                "h_nm": float(args.h_nm),
                "modal_degree": int(args.modal_degree),
                "modal_h_nm": float(args.modal_h_nm),
                "requested_modes_per_direction": int(args.requested_modes),
                "candidate_modes_per_direction": int(args.candidate_modes),
                "polarization_kind": args.polarization_kind,
                "incident_grazing_deg": float(args.incident_grazing_deg),
                "bottom_interface_nm": float(args.bottom_interface_nm),
                "top_interface_nm": float(args.top_interface_nm),
                "stage4_full3d_assembly_backend": (
                    args.stage4_full3d_assembly_backend
                ),
                "internal_propagation_model": args.internal_propagation_model,
                "internal_traction_model": args.internal_traction_model,
                "solver_path": args.solver_path,
            },
            "hybrid_system": {
                "candidate_global_block_action": "not_constructed_early_path",
                "global_A_materialized": False,
                "bottom_global_F_materialized": False,
                "top_global_F_materialized": False,
                "external_C_D_materialized": False,
                "external_auxiliary_in_krylov": False,
            },
            "solve": {
                "h5a": h5a_sides,
                "h5b": h5b_sides,
                "reported_relative_residual": "see h5_telemetry",
                "true_relative_residual": "see h5_telemetry",
            },
            "validation": {
                "port_power": "not_run",
                "external_diffraction_orders": "not_run",
                "field_reconstruction": "not_run",
            },
            "official_record": False,
            "h5_telemetry": h5_telemetry,
            "gates": {
                "h5a_all_22_direct_residuals_le_1e-10": h5a_pass,
                "h5b_all_22_rhs_twice_pass": h5b_pass,
                "h5_worker_numerical_pass": h5_pass,
                "h5_swap": "not_evaluated_external_watchdog",
                "h5_no_direct_fallback": (
                    h5_no_direct_fallback
                ),
            },
            "qualification": {
                "task037b_h5_gate": True,
                "integration_pass": h5_pass,
                "worker_numerical_pass": h5_pass,
                "swap_status": "not_evaluated_external_watchdog",
                "official_record": False,
                "boundary": (
                    "H5 local inverse qualification only; R/T/A, field and "
                    "12+12 physics are not run in this early path."
                ),
            },
            "timing_seconds_max_rank": {
                **timings,
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": comm.gather(
                _historical_peak_rss_mb(), root=0
            ),
            "memory_semantics": (
                "H5a direct-reference and H5b candidate stages are separated; "
                "swap is evaluated by the external watchdog."
            ),
        }
        raise _H5QualificationStop(record)
    finally:
        if bottom_inverse is not None:
            bottom_inverse.destroy()
        if top_inverse is not None:
            top_inverse.destroy()
        for rhs_list in rhs_sets.values():
            for _name, vector, _metadata in rhs_list:
                vector.destroy()
        for side_references in direct_references.values():
            for vector in side_references.values():
                vector.destroy()


def main() -> None:
    args = _parse_args()
    if args.h_nm <= 0.0:
        raise SystemExit("--h-nm must be positive.")
    modal_h_nm = float(args.h_nm) if args.modal_h_nm is None else float(args.modal_h_nm)
    modal_degree = (
        int(args.degree) if args.modal_degree is None else int(args.modal_degree)
    )
    if modal_h_nm <= 0.0:
        raise SystemExit("--modal-h-nm must be positive.")
    if not (0.0 < args.bottom_interface_nm < args.top_interface_nm < 120.0):
        raise SystemExit(
            "Task33 buffer interfaces must satisfy "
            "0 < bottom-interface-nm < top-interface-nm < 120."
        )
    if args.graded_reference_h is not None:
        if args.modal_h_nm is not None or args.modal_degree is not None:
            raise SystemExit(
                "Independent modal h/p is not combined with the Task034 "
                "graded local-mesh research path."
            )
        if args.degree not in (2, 3):
            raise SystemExit("The Task034 fixed-p graded path is restricted to p2/p3.")
        if args.bottom_interface_nm != 10.0 or args.top_interface_nm != 110.0:
            raise SystemExit(
                "The first Task033 graded path is qualified only at the "
                "reviewed 10/110 nm matching interfaces."
            )
        if not np.isclose(args.h_nm, args.graded_reference_h):
            raise SystemExit("--h-nm must equal --graded-reference-h.")
        if args.graded_coarse_factor <= 1.0:
            raise SystemExit("--graded-coarse-factor must be greater than one.")
    if not 0.0 < args.incident_grazing_deg < 90.0:
        raise SystemExit("--incident-grazing-deg must lie strictly between 0 and 90.")
    if args.requested_modes < 2:
        raise SystemExit("--requested-modes must be at least 2.")
    candidate_modes = (
        int(args.candidate_modes)
        if args.candidate_modes is not None
        else (
            int(args.requested_modes)
            if args.requested_modes <= 6
            else 2 * int(args.requested_modes)
        )
    )
    if candidate_modes < args.requested_modes:
        raise SystemExit("--candidate-modes must be at least --requested-modes.")
    if args.near_degenerate_tolerance <= 0.0:
        raise SystemExit("--near-degenerate-tolerance must be positive.")
    if args.block_rotation_tolerance <= 0.0:
        raise SystemExit("--block-rotation-tolerance must be positive.")
    if args.compare_modal_schur and args.solver_path != "augmented":
        raise SystemExit("--compare-modal-schur requires --solver-path augmented.")
    if (
        args.internal_traction_model == "scalar_cg_discrete_derivative"
        and args.internal_propagation_model != "full3d_uniform_cg"
    ):
        raise SystemExit(
            "scalar_cg_discrete_derivative traction requires "
            "--internal-propagation-model full3d_uniform_cg."
        )
    task33_variant = bool(
        args.degree != 2
        or modal_degree != args.degree
        or not np.isclose(modal_h_nm, args.h_nm)
        or args.bottom_interface_nm != 10.0
        or args.top_interface_nm != 110.0
        or args.graded_reference_h is not None
        or not np.isclose(args.incident_grazing_deg, 10.0)
        or args.polarization_kind != "s"
        or args.internal_propagation_model != "continuous_beta"
        or args.internal_traction_model != "continuous_qep_beta"
    )
    comm = MPI.COMM_WORLD
    provenance = _source_provenance(
        comm, args.verified_clean_sha, args.allow_dirty_research
    )
    if (
        args.task035c_p6_h10_gate
        or args.task037b_h1_gate
        or args.task037b_h3_gate
        or args.task037b_h4_gate
        or args.task037b_h5_gate
    ) and comm.size not in TASK035C_P6_H10_MPI_SIZES:
        raise SystemExit("Task035c p6/h10 Hybrid is restricted to MPI1/2/4/8.")
    if (
        args.task037b_h1_gate
        or args.task037b_h3_gate
        or args.task037b_h4_gate
        or args.task037b_h5_gate
    ) and comm.size != 8:
        raise SystemExit("Task037b H1/H3/H4/H5 Hybrid is restricted to MPI8.")
    task035c_p6_gate = _task035c_worker_authority_gate(
        args,
        current_source_sha=provenance.get("commit_sha"),
        mpi_size=comm.size,
    )

    if comm.rank == 0 and args.memory_stages is not None:
        args.memory_stages.parent.mkdir(parents=True, exist_ok=True)
        args.memory_stages.unlink(missing_ok=True)
    comm.barrier()

    def mark_stage(stage: str) -> None:
        if comm.rank == 0 and args.memory_stages is not None:
            with args.memory_stages.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(
                        {
                            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                            "stage": stage,
                            "elapsed_seconds": time.perf_counter() - total_started,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    def progress(message: str) -> None:
        if comm.rank == 0:
            print(message, flush=True)

    total_started = time.perf_counter()
    timings: dict[str, float] = {}
    h1_telemetry = None
    cfg = target_stage4_config(degree=args.degree, h_nm=args.h_nm)
    cfg.stage4_full3d_assembly_backend = args.stage4_full3d_assembly_backend
    cfg.matrix_diagnostics_assemble_only = False
    cfg.matrix_diagnostics_factorization_only = False
    cfg.incident_theta_deg = 90.0 - float(args.incident_grazing_deg)
    cfg.polarization_kind = args.polarization_kind
    modal_cfg = target_stage4_config(
        degree=modal_degree,
        h_nm=modal_h_nm,
    )
    modal_cfg.incident_theta_deg = cfg.incident_theta_deg
    modal_cfg.incident_phi_deg = cfg.incident_phi_deg
    modal_cfg.polarization_kind = cfg.polarization_kind
    operators = None
    positive = None
    negative = None
    bottom = None
    top = None
    coupling = None
    system = None
    solution = None
    schur_system = None
    schur_solution = None
    primary_schur_system = None
    h3_oracle_bottom = None
    h3_oracle_top = None
    h3_direct_bottom = None
    h3_direct_top = None
    h3_preconditioner = None
    h3_solve_result = None
    h3_direct_comparison_system = None
    h3_direct_comparison_solution = None
    h3_candidate_bottom = None
    h3_candidate_top = None
    h3_bottom_auxiliary_vec = None
    h3_top_auxiliary_vec = None
    h3_before_inventory = None
    h3_after_inventory = None
    h3_direct_factor_inventory = None
    h3_solution_error = None
    h3_modal_error = None
    h3_telemetry = None
    h4b_preconditioner = None
    h4b_solve_result = None
    h4_telemetry = None
    h4a_modal_diagnostic = None
    h4b_modal_diagnostic = None
    h4b_before_inventory = None
    h4b_after_inventory = None
    h4b_solution_error = None
    h4b_modal_error = None
    h4b_finite = None
    h4_diagnostic_finite = None
    record = None
    graded_plan = None
    graded_bottom_mesh = None
    graded_top_mesh = None

    def finite_spectrum_capacity_record(
        *,
        direction: str,
        selection,
        solver_report,
    ) -> dict[str, Any]:
        """Preserve a clean measured negative when singular K2 yields infinity roots."""

        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        rss = comm.gather(_historical_peak_rss_mb(), root=0)
        timestamp = datetime.now(timezone.utc).isoformat()
        case = {
            "material_kind": "stage4_xy",
            "degree": args.degree,
            "h_nm": args.h_nm,
            "modal_degree": modal_degree,
            "modal_h_nm": modal_h_nm,
            "internal_propagation_model": (args.internal_propagation_model),
            "internal_traction_model": args.internal_traction_model,
            "discrete_axial_qualification_scope": (
                _discrete_axial_qualification_scope(
                    args.internal_propagation_model,
                    args.internal_traction_model,
                )
            ),
            "requested_modes_per_direction": args.requested_modes,
            "candidate_modes_per_target_branch": candidate_modes,
            "near_degenerate_tolerance": args.near_degenerate_tolerance,
            "block_rotation_tolerance": args.block_rotation_tolerance,
            "bottom_interface_nm": args.bottom_interface_nm,
            "top_interface_nm": args.top_interface_nm,
            "middle_length_nm": args.top_interface_nm - args.bottom_interface_nm,
            "wavelength_nm": cfg.lambda0,
            "incident_grazing_deg": 90.0 - cfg.incident_theta_deg,
            "polarization_kind": cfg.polarization_kind,
            "mesh_policy": "reviewed_stage4_axis_plan",
            "graded_reference_h_nm": args.graded_reference_h,
            "graded_coarse_factor": None,
            "graded_plan_hash": None,
            "graded_plan": None,
        }
        selection_record = _directional_selection_summary(selection)
        capacity = {
            "status": "insufficient_finite_admissible_modes",
            "direction": direction,
            "requested_modes_per_direction": args.requested_modes,
            "delivered_finite_admissible_modes": selection.selected_modes,
            "finite_candidate_count_both_directions": (
                selection.finite_candidate_count
            ),
            "numerically_infinite_candidate_count": (
                selection.numerically_infinite_candidate_count
            ),
            "finite_spectrum_abs_beta_h_cutoff": (NUMERICAL_INFINITY_BETA_H_CUTOFF),
            "finite_spectrum_abs_beta_cutoff_per_nm": (selection.abs_beta_cutoff),
            "first_rejected_numerical_infinity_beta_per_nm": (
                selection_record["first_rejected_numerical_infinity_beta_per_nm"]
            ),
            "leading_coefficient_singular_by_design": (
                operators.leading_coefficient_singular_by_design
            ),
            "pair_tolerance_relaxed": False,
            "left_pair_relative_error_tolerance": 1.0e-7,
        }
        return {
            "schema_version": 1,
            "benchmark_id": "task033_hybrid_modal_basis_capacity",
            "timestamp_utc": timestamp,
            "status": "insufficient_finite_admissible_modes",
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task032_phase6_augmented "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "full_field_or_mode_vector_gather": False,
                "primary_solver_path": args.solver_path,
                "internal_propagation_model_requested": (
                    args.internal_propagation_model
                ),
                "internal_traction_model_requested": (args.internal_traction_model),
                "stage4_full3d_assembly_backend_requested": (
                    args.stage4_full3d_assembly_backend
                ),
                "task035c_p6_h10_authority_gate": task035c_p6_gate,
                "task33_variant": True,
                "provenance": (
                    "clean_task033_finite_spectrum_capacity_negative"
                    if not provenance["tracked_source_dirty"]
                    else "dirty_task033_finite_spectrum_capacity_research"
                ),
            },
            "case": case,
            "qep": {
                "target_beta_per_nm": _complex_json(target),
                "full_shape": list(operators.full_shape),
                "reduced_shape": list(operators.reduced_shape),
                "field_degree": operators.field_degree,
                "geometry_degree": operators.geometry_degree,
                "coefficient_degree": operators.coefficient_degree,
                "quadrature_degree": operators.quadrature_degree,
                "quadrature_policy": operators.quadrature_policy,
                f"{direction}_solver_converged_modes": (solver_report.converged_modes),
                f"{direction}_directional_selection": selection_record,
            },
            "hybrid_system": {
                "primary_solver_path": args.solver_path,
                "dense_interface_square_formed": False,
                "full_field_or_mode_gathered": False,
            },
            "solve": {"true_relative_residual": None},
            "validation": {
                "port_power": None,
                "external_diffraction_orders": None,
            },
            "physical_field_reconstruction": None,
            "modal_schur_comparison": None,
            "object_payload_ledger": {
                "mode_count_per_direction": selection.selected_modes,
                "storage_complexity_contract": "O(N_interface*M)+O(M^2)",
                "dense_interface_square_formed": False,
            },
            "full3d_reference_comparison": None,
            "gates": {"finite_admissible_mode_capacity": False},
            "qualification": {
                "integration_pass": False,
                "algebraic_chain_pass": False,
                "task033_physical_truncation_allowed": False,
                "clean_source_integration_record": False,
                "physical_augmented_direct_pass": False,
                "mode_count_converged": False,
                "physical_field_gates_pass": False,
                "modal_basis_capacity_pass": False,
                "capacity_disposition": "insufficient_finite_admissible_modes",
                "official_record": False,
                "boundary": (
                    "Measured finite-spectrum capacity negative; numerical-infinity "
                    "roots from singular K2 are rejected before adjoint pairing."
                ),
            },
            "modal_basis_capacity": capacity,
            "timing_seconds_max_rank": {
                **timings,
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": rss,
            "memory_semantics": (
                "per-rank ru_maxrss historical peaks; not simultaneous RSS"
            ),
        }

    try:
        mark_stage("cross_section_eigen_assembly")
        started = time.perf_counter()
        if args.graded_reference_h is not None:
            from src.geometry.task034_adaptive_mesh import (
                Task034Stage4Geometry,
                build_task034_conforming_graded_plan,
                build_task034_graded_local_mesh_pair,
            )

            graded_plan = build_task034_conforming_graded_plan(
                reference_h_nm=args.graded_reference_h,
                geometry=Task034Stage4Geometry.from_config(
                    cfg,
                    bottom_interface_z_nm=args.bottom_interface_nm,
                    top_interface_z_nm=args.top_interface_nm,
                ),
                profile=args.graded_profile,
                coarse_factor=args.graded_coarse_factor,
                comm_size=comm.size,
            )
            graded_bottom_mesh, graded_top_mesh = build_task034_graded_local_mesh_pair(
                cfg, graded_plan
            )
            cross_section = build_matching_cross_section(
                cfg,
                "stage4_xy",
                x_values=graded_plan.x_values,
                y_values=graded_plan.y_values,
            )
        else:
            cross_section = build_matching_cross_section(
                modal_cfg,
                "stage4_xy",
            )
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=modal_degree
        )
        operators = assemble_quadratic_beta_operators(modal_cfg, cross_section, spaces)
        poynting_evaluator = PoyntingFluxEvaluator(modal_cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(modal_cfg, modal_cfg.n_air)
        timings["cross_section_and_qep_assembly"] = _max_elapsed(comm, started)
        progress("Task32 Phase6: cross-section QEP assembled")

        mark_stage("cross_section_eigen_solve")
        started = time.perf_counter()
        positive_right, positive_report = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=candidate_modes,
        )
        progress("Task32 Phase6: positive right QEP modes complete")
        positive_right, positive_selection = select_passive_direction_modes(
            positive_right,
            desired_direction="forward",
            requested_modes=args.requested_modes,
            poynting_evaluator=poynting_evaluator,
            maximum_abs_beta=(NUMERICAL_INFINITY_BETA_H_CUTOFF / modal_h_nm),
        )
        if len(positive_right) != args.requested_modes:
            for mode in positive_right:
                mode.destroy()
            if positive_selection.numerically_infinite_candidate_count:
                record = finite_spectrum_capacity_record(
                    direction="positive",
                    selection=positive_selection,
                    solver_report=positive_report,
                )
                raise _ModalBasisCapacityStop
            raise RuntimeError(
                "Positive finite candidate pool did not deliver enough passive "
                f"forward modes: {positive_selection.direction_counts}."
            )
        mark_stage("mode_classification")
        positive = build_biorthogonal_mode_basis(
            modal_cfg,
            cross_section,
            spaces,
            operators,
            positive_right,
            adjoint_target=np.conj(target),
            requested_left_modes=candidate_modes,
            near_degenerate_tolerance=args.near_degenerate_tolerance,
            block_rotation_tolerance=args.block_rotation_tolerance,
            poynting_evaluator=poynting_evaluator,
            log=progress,
        )
        progress("Task32 Phase6: positive adjoint basis complete")
        negative_right, negative_report = solve_quadratic_beta_modes(
            operators,
            target=-target,
            requested_modes=candidate_modes,
        )
        progress("Task32 Phase6: negative right QEP modes complete")
        negative_right, negative_selection = select_passive_direction_modes(
            negative_right,
            desired_direction="backward",
            requested_modes=args.requested_modes,
            poynting_evaluator=poynting_evaluator,
            maximum_abs_beta=(NUMERICAL_INFINITY_BETA_H_CUTOFF / modal_h_nm),
        )
        if len(negative_right) != args.requested_modes:
            for mode in negative_right:
                mode.destroy()
            if negative_selection.numerically_infinite_candidate_count:
                record = finite_spectrum_capacity_record(
                    direction="negative",
                    selection=negative_selection,
                    solver_report=negative_report,
                )
                raise _ModalBasisCapacityStop
            raise RuntimeError(
                "Negative finite candidate pool did not deliver enough passive "
                f"backward modes: {negative_selection.direction_counts}."
            )
        negative = build_biorthogonal_mode_basis(
            modal_cfg,
            cross_section,
            spaces,
            operators,
            negative_right,
            adjoint_target=-np.conj(target),
            requested_left_modes=candidate_modes,
            near_degenerate_tolerance=args.near_degenerate_tolerance,
            block_rotation_tolerance=args.block_rotation_tolerance,
            poynting_evaluator=poynting_evaluator,
            log=progress,
        )
        progress("Task32 Phase6: negative adjoint basis complete")
        progress(
            "Task32 Phase6: delivered basis counts "
            f"positive={len(positive.modes)}/{positive_report.converged_modes}, "
            f"negative={len(negative.modes)}/{negative_report.converged_modes}"
        )
        preview_count = min(len(positive.modes), 12)
        progress(
            "Task32 Phase6: positive beta preview "
            f"{[complex(mode.beta) for mode in positive.modes[:preview_count]]} "
            f"(showing {preview_count}/{len(positive.modes)})"
        )
        progress(
            "Task32 Phase6: positive near-degenerate group count "
            f"{len(positive.groups)}; first groups="
            f"{[group.indices for group in positive.groups[:8]]}"
        )
        pairs = pair_reciprocal_mode_bases(operators, positive, negative)
        timings["positive_and_negative_biorthogonal_bases"] = _max_elapsed(
            comm, started
        )
        progress("Task32 Phase6: real positive/negative QEP bases complete")

        if (
            args.task037b_h3_gate
            or args.task037b_h4_gate
            or args.task037b_h5_gate
        ):
            mark_stage("oracle_local_matrix_build")
            started = time.perf_counter()
            h3_direct_bottom = assemble_hybrid_local_dtn_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
                local_mesh_override=graded_bottom_mesh,
            )
            h3_oracle_bottom = _h3_oracle_local_system(h3_direct_bottom)
            h3_direct_bottom.destroy()
            h3_direct_bottom = None
            h3_direct_top = assemble_hybrid_local_dtn_system(
                cfg,
                "top",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
                local_mesh_override=graded_top_mesh,
            )
            h3_oracle_top = _h3_oracle_local_system(h3_direct_top)
            h3_direct_top.destroy()
            h3_direct_top = None
            timings["oracle_local_matrix_build"] = _max_elapsed(comm, started)
            if args.task037b_h5_gate:
                mark_stage("h5_action_coupling_build")
            else:
                mark_stage("h2b_action_assembly")
            started = time.perf_counter()
            bottom = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
                local_mesh_override=h3_oracle_bottom.local_mesh,
                log=progress,
            )
            top = assemble_hybrid_local_dtn_action_system(
                cfg,
                "top",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
                local_mesh_override=h3_oracle_top.local_mesh,
                log=progress,
            )
            coupling = build_hybrid_internal_mode_coupling(
                cfg,
                spaces,
                positive,
                negative,
                bottom,
                top,
                length_nm=args.top_interface_nm - args.bottom_interface_nm,
                propagation_model=args.internal_propagation_model,
                modal_traction_model=args.internal_traction_model,
                log=progress,
            )
            if args.task037b_h5_gate:
                timings["h5_action_coupling_build"] = _max_elapsed(
                    comm, started
                )
            if args.task037b_h5_gate:
                _run_h5_local_qualification(
                    args=args,
                    comm=comm,
                    provenance=provenance,
                    authority_gate=task035c_p6_gate,
                    cfg=cfg,
                    positive=positive,
                    negative=negative,
                    bottom=bottom,
                    top=top,
                    coupling=coupling,
                    oracle_bottom=h3_oracle_bottom,
                    oracle_top=h3_oracle_top,
                    timings=timings,
                    total_started=total_started,
                    mark_stage=mark_stage,
                    progress=progress,
                )
            layout = HybridAugmentedLayout.build(
                bottom,
                top,
                coupling.internal_unknown_count,
            )
            action_matrix, action_context = create_hybrid_assembled_block_action(
                bottom,
                top,
                coupling,
            )
            action_inventory = dict(action_context.inventory)
            system = HybridBlockActionSystem(
                A=action_matrix,
                b=layout.pack(
                    bottom.b,
                    top.b,
                    internal_modal_rhs_correction(coupling),
                ),
                layout=layout,
                context=action_context,
                inventory=action_inventory,
                matrix_stats=_petsc_matrix_stats(action_matrix, assemble=False),
                block_shapes={
                    "A_bottom": bottom.A.getSize(),
                    "A_top": top.A.getSize(),
                    "global_action": action_matrix.getSize(),
                },
                inserted_nnz_by_block={"action_only": None},
            )
            if not args.task037b_h5_gate:
                timings["h2b_action_assembly"] = _max_elapsed(comm, started)
            mark_stage("h3_local_factor_setup")
            started = time.perf_counter()
            h3_preconditioner = create_exact_block_ldu_preconditioner(
                layout,
                h3_oracle_bottom,
                h3_oracle_top,
                coupling,
            )
            h3_before_inventory = {
                **h3_preconditioner.inventory,
                "factor_inventory": h3_preconditioner.modal_schur_system.factor_inventory,
                "modal_schur_bytes": int(h3_preconditioner.modal_schur.nbytes),
                "modal_schur_condition": float(
                    h3_preconditioner.modal_schur_system.modal_schur_condition
                ),
            }
            timings["h3_local_factor_setup"] = _max_elapsed(comm, started)
            mark_stage("h3_outer_solve")
            started = time.perf_counter()
            h3_solve_result = solve_exact_block_ldu(
                system.A,
                system.b,
                h3_preconditioner,
            )
            h3_after_inventory = {
                **h3_preconditioner.inventory,
                "modal_schur_bytes": int(h3_preconditioner.modal_schur.nbytes),
                "modal_schur_condition": float(
                    h3_preconditioner.modal_schur_system.modal_schur_condition
                ),
            }
            if not h3_preconditioner.factors_released:
                raise RuntimeError("H3 factors were not released after solve.")
            timings["h3_outer_solve"] = _max_elapsed(comm, started)
            mark_stage("h3_factors_released")
            if args.task037b_h4_gate:
                h4a_modal_diagnostic = modal_block_diagnostic(
                    h3_preconditioner.modal_schur_system
                )
                mark_stage("h4b_g_only_factor_setup")
                started = time.perf_counter()
                h4b_preconditioner = create_g_only_block_ldu_preconditioner(
                    layout,
                    h3_oracle_bottom,
                    h3_oracle_top,
                    coupling,
                )
                h4b_modal_diagnostic = modal_block_diagnostic(
                    h4b_preconditioner.modal_schur_system
                )
                h4b_before_inventory = {
                    **h4b_preconditioner.inventory,
                    "factor_inventory": (
                        h4b_preconditioner.modal_schur_system.factor_inventory
                    ),
                    "modal_schur_bytes": int(h4b_preconditioner.modal_schur.nbytes),
                    "modal_schur_condition": float(
                        h4b_preconditioner.modal_schur_system.modal_schur_condition
                    ),
                }
                timings["h4b_g_only_factor_setup"] = _max_elapsed(comm, started)
                mark_stage("h4b_g_only_solve")
                started = time.perf_counter()
                h4b_solve_result = solve_exact_block_ldu(
                    system.A,
                    system.b,
                    h4b_preconditioner,
                )
                h4b_after_inventory = {
                    **h4b_preconditioner.inventory,
                    "modal_schur_bytes": int(h4b_preconditioner.modal_schur.nbytes),
                    "modal_schur_condition": float(
                        h4b_preconditioner.modal_schur_system.modal_schur_condition
                    ),
                }
                timings["h4b_g_only_solve"] = _max_elapsed(comm, started)
                mark_stage("h4b_factors_released")
                h4b_bottom, h4b_top, h4b_modal = layout.split(
                    h4b_solve_result.solution,
                    bottom.b,
                    top.b,
                )
                h4a_bottom, h4a_top, h4a_modal = layout.split(
                    h3_solve_result.solution,
                    bottom.b,
                    top.b,
                )
                try:
                    h4b_solution_error = _relative_vector_error(
                        h4b_solve_result.solution,
                        h3_solve_result.solution,
                    )
                    h4b_modal_error = float(
                        np.linalg.norm(h4b_modal - h4a_modal)
                        / max(
                            float(np.linalg.norm(h4a_modal)),
                            float(np.linalg.norm(h4b_modal)),
                            1.0e-30,
                        )
                    )
                finally:
                    h4b_bottom.destroy()
                    h4b_top.destroy()
                    h4a_bottom.destroy()
                    h4a_top.destroy()
                h4b_finite = bool(
                    np.isfinite(h4b_solution_error)
                    and np.isfinite(h4b_modal_error)
                    and np.isfinite(h4b_solve_result.true_relative_residual)
                    and all(
                        np.isfinite(value)
                        for value in h4b_solve_result.block_relative_residuals.values()
                    )
                    and np.isfinite(h4b_solve_result.solution.norm())
                )
                h4_diagnostic_finite = bool(
                    all(
                        np.isfinite(float(h4a_modal_diagnostic[key]))
                        for key in (
                            "exact_s_m_condition",
                            "g_condition",
                            "feedback_frobenius_norm",
                            "feedback_relative_to_s_m",
                            "feedback_relative_to_g",
                        )
                    )
                    and all(
                        np.isfinite(float(h4b_modal_diagnostic[key]))
                        for key in (
                            "exact_s_m_condition",
                            "g_condition",
                            "feedback_frobenius_norm",
                            "feedback_relative_to_s_m",
                            "feedback_relative_to_g",
                        )
                    )
                    and np.isfinite(h3_solve_result.reported_relative_residual)
                    and np.isfinite(h4b_solve_result.reported_relative_residual)
                )
                h4_telemetry = {
                    "task037b_h4_gate": True,
                    "h4a_exact_s_m": h4a_modal_diagnostic,
                    "h4b_g_only": h4b_modal_diagnostic,
                    "feedback": {
                        "frobenius_norm": h4a_modal_diagnostic["feedback_frobenius_norm"],
                        "relative_to_s_m": h4a_modal_diagnostic["feedback_relative_to_s_m"],
                        "relative_to_g": h4a_modal_diagnostic["feedback_relative_to_g"],
                    },
                    "h4a": {
                        "outer_iterations": int(h3_solve_result.iterations),
                        "converged_reason": int(h3_solve_result.converged_reason),
                        "reported_relative_residual": float(
                            h3_solve_result.reported_relative_residual
                        ),
                        "true_relative_residual": float(
                            h3_solve_result.true_relative_residual
                        ),
                        "block_relative_residuals": h3_solve_result.block_relative_residuals,
                        "factors_released": bool(h3_preconditioner.factors_released),
                        "preconditioner_before": h3_before_inventory,
                        "preconditioner_after": h3_after_inventory,
                    },
                    "h4b": {
                        "outer_iterations": int(h4b_solve_result.iterations),
                        "converged_reason": int(h4b_solve_result.converged_reason),
                        "reported_relative_residual": float(
                            h4b_solve_result.reported_relative_residual
                        ),
                        "true_relative_residual": float(
                            h4b_solve_result.true_relative_residual
                        ),
                        "block_relative_residuals": h4b_solve_result.block_relative_residuals,
                        "solution_relative_error_to_h4a": float(h4b_solution_error),
                        "modal_relative_error_to_h4a": float(h4b_modal_error),
                        "finite": h4b_finite,
                        "factors_released": bool(h4b_preconditioner.factors_released),
                        "preconditioner_before": h4b_before_inventory,
                        "preconditioner_after": h4b_after_inventory,
                    },
                    "diagnostic_finite": h4_diagnostic_finite,
                    "timings": {
                        key: timings[key]
                        for key in (
                            "h4b_g_only_factor_setup",
                            "h4b_g_only_solve",
                        )
                        if key in timings
                    },
                }
                h4b_solve_result.destroy()
                h4b_solve_result = None
                h4b_preconditioner = None
            mark_stage("post_h3_direct_comparison")
            started = time.perf_counter()
            h3_direct_comparison_system = build_hybrid_augmented_direct_system(
                h3_oracle_bottom,
                h3_oracle_top,
                coupling,
            )
            h3_direct_comparison_solution = solve_hybrid_augmented_direct(
                h3_direct_comparison_system,
                h3_oracle_bottom,
                h3_oracle_top,
                None,
            )
            h3_solution_error = _relative_vector_error(
                h3_solve_result.solution,
                h3_direct_comparison_solution.x,
            )
            candidate_bottom, candidate_top, candidate_modal = layout.split(
                h3_solve_result.solution,
                bottom.b,
                top.b,
            )
            h3_candidate_bottom = candidate_bottom
            h3_candidate_top = candidate_top
            h3_modal_error = float(
                np.linalg.norm(
                    candidate_modal - h3_direct_comparison_solution.modal_amplitudes
                )
                / max(
                    float(np.linalg.norm(candidate_modal)),
                    float(
                        np.linalg.norm(
                            h3_direct_comparison_solution.modal_amplitudes
                        )
                    ),
                    1.0e-30,
                )
            )
            h3_direct_factor_inventory = _petsc_factor_inventory(
                h3_direct_comparison_solution.ksp
            )
            h3_direct_comparison_solution.destroy()
            h3_direct_comparison_solution = None
            h3_direct_comparison_system.destroy()
            h3_direct_comparison_system = None
            h3_oracle_bottom.destroy()
            h3_oracle_bottom = None
            h3_oracle_top.destroy()
            h3_oracle_top = None
            timings["post_h3_direct_comparison"] = _max_elapsed(comm, started)
            h3_bottom_auxiliary_vec = recover_petsc_auxiliary(
                bottom.blocks,
                candidate_bottom,
            )
            h3_top_auxiliary_vec = recover_petsc_auxiliary(top.blocks, candidate_top)
            bottom_auxiliary = _h3_replicated_vec_values(h3_bottom_auxiliary_vec)
            top_auxiliary = _h3_replicated_vec_values(h3_top_auxiliary_vec)
            h3_bottom_auxiliary_vec.destroy()
            h3_bottom_auxiliary_vec = None
            h3_top_auxiliary_vec.destroy()
            h3_top_auxiliary_vec = None
            mark_stage("recovery_rta")
            started = time.perf_counter()
            bottom_recovered = recover_hybrid_static_local_field(
                bottom,
                coupling,
                candidate_bottom,
                candidate_modal,
                auxiliary_override=bottom_auxiliary,
            )
            top_recovered = recover_hybrid_static_local_field(
                top,
                coupling,
                candidate_top,
                candidate_modal,
                auxiliary_override=top_auxiliary,
            )
            timings["recovery_rta"] = _max_elapsed(comm, started)
            solution = HybridBlockLduPhysicalSolution(
                bottom=candidate_bottom,
                top=candidate_top,
                modal_amplitudes=np.asarray(candidate_modal, dtype=np.complex128),
                bottom_auxiliary=bottom_auxiliary,
                top_auxiliary=top_auxiliary,
                bottom_recovered=bottom_recovered,
                top_recovered=top_recovered,
                factor_solver="exact_block_ldu",
                converged_reason=h3_solve_result.converged_reason,
                reported_relative_residual=h3_solve_result.reported_relative_residual,
                relative_residual=h3_solve_result.true_relative_residual,
                block_relative_residuals=h3_solve_result.block_relative_residuals,
                iterations=h3_solve_result.iterations,
                setup_seconds=timings["h3_local_factor_setup"],
                solve_seconds=timings["h3_outer_solve"],
                recovery_seconds=timings["recovery_rta"],
            )
            h3_candidate_bottom = None
            h3_candidate_top = None
            h3_solve_result.destroy()
            h3_solve_result = None
            timings["primary_system_build"] = timings["h2b_action_assembly"]
        else:
            mark_stage("local_fem_dtn_assembly")
            started = time.perf_counter()
            bottom = assemble_hybrid_local_dtn_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
                local_mesh_override=graded_bottom_mesh,
            )
            top = assemble_hybrid_local_dtn_system(
                cfg,
                "top",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
                local_mesh_override=graded_top_mesh,
            )
            timings["two_local_fem_dtn_systems"] = _max_elapsed(comm, started)
            progress("Task32 Phase6: bottom/top local FEM-DtN systems complete")

            mark_stage("interface_projection_and_coupling")
            started = time.perf_counter()
            coupling = build_hybrid_internal_mode_coupling(
                cfg,
                spaces,
                positive,
                negative,
                bottom,
                top,
                length_nm=args.top_interface_nm - args.bottom_interface_nm,
                propagation_model=args.internal_propagation_model,
                modal_traction_model=args.internal_traction_model,
                log=progress,
            )
            timings["internal_modal_coupling"] = _max_elapsed(comm, started)

            started = time.perf_counter()
            if args.solver_path == "augmented":
                mark_stage("augmented_matrix_and_factor")
                system = build_hybrid_augmented_direct_system(bottom, top, coupling)
                timings["primary_system_build"] = _max_elapsed(comm, started)
                timings["monolithic_assembly"] = timings["primary_system_build"]
                progress("Task32 Phase6: monolithic augmented AIJ complete")
                solution = solve_hybrid_augmented_direct(
                    system,
                    bottom,
                    top,
                    coupling,
                )
            else:
                builder = (
                    build_hybrid_modal_schur_direct_system
                    if args.solver_path == "modal-schur-fast"
                    else build_hybrid_modal_schur_memory_minimal_system
                )
                primary_schur_system = builder(
                    bottom, top, coupling, stage_callback=mark_stage
                )
                timings["primary_system_build"] = _max_elapsed(comm, started)
                progress(
                    "Task32 Phase10: standalone "
                    f"{primary_schur_system.lifecycle_strategy} Schur system complete"
                )
                solution = solve_hybrid_modal_schur_direct(
                    primary_schur_system,
                    bottom,
                    top,
                    coupling,
                    stage_callback=mark_stage,
                )
        mark_stage("official_rta")
        rta_started = time.perf_counter()
        if args.task037b_h3_gate or args.task037b_h4_gate:
            validation = evaluate_hybrid_augmented_solution(
                cfg,
                bottom,
                top,
                coupling,
                solution,
                auxiliary_override=(
                    solution.bottom_auxiliary,
                    solution.top_auxiliary,
                ),
            )
        else:
            validation = evaluate_hybrid_augmented_solution(
                cfg, bottom, top, coupling, solution
            )
        if args.task037b_h1_gate or args.task037b_h3_gate or args.task037b_h4_gate:
            timings["rta_evaluation"] = _max_elapsed(comm, rta_started)
        port_power = validation["port_power"]
        modal_schur_comparison = None
        if args.compare_modal_schur:
            started = time.perf_counter()
            comparison_builder = (
                build_hybrid_modal_schur_direct_system
                if args.comparison_solver_path == "fast"
                else build_hybrid_modal_schur_memory_minimal_system
            )
            comparison_solver_path = (
                "modal-schur-fast"
                if args.comparison_solver_path == "fast"
                else "modal-schur-memory-minimal"
            )
            schur_system = comparison_builder(bottom, top, coupling)
            timings["modal_schur_build"] = _max_elapsed(comm, started)
            schur_solution = solve_hybrid_modal_schur_direct(
                schur_system, bottom, top, coupling
            )
            schur_validation = evaluate_hybrid_augmented_solution(
                cfg, bottom, top, coupling, schur_solution
            )
            modal_difference = np.asarray(
                schur_solution.modal_amplitudes - solution.modal_amplitudes,
                dtype=np.complex128,
            )
            modal_scale = max(
                float(np.linalg.norm(schur_solution.modal_amplitudes)),
                float(np.linalg.norm(solution.modal_amplitudes)),
                1.0e-30,
            )
            rta_delta = {
                key: float(
                    schur_validation["port_power"][key] - validation["port_power"][key]
                )
                for key in ("R_total", "T_total", "A_balance")
            }
            comparison_gates = {
                "modal_coefficients_relative_error_le_1e-9": (
                    float(np.linalg.norm(modal_difference) / modal_scale) <= 1.0e-9
                ),
                "bottom_solution_relative_error_le_1e-9": (
                    _relative_vector_error(schur_solution.bottom, solution.bottom)
                    <= 1.0e-9
                ),
                "top_solution_relative_error_le_1e-9": (
                    _relative_vector_error(schur_solution.top, solution.top) <= 1.0e-9
                ),
                "modal_schur_full_residual_le_1e-9": (
                    schur_solution.relative_residual <= 1.0e-9
                    and schur_solution.modal_relative_residual <= 1.0e-9
                ),
                "rta_absolute_delta_le_1e-10": max(
                    abs(value) for value in rta_delta.values()
                )
                <= 1.0e-10,
                "no_dense_interface_square": (
                    not schur_system.dense_interface_square_formed
                ),
                "multi_rhs_single_factor_context_per_local_block": (
                    schur_system.multi_rhs_count == 2 * args.requested_modes + 1
                ),
            }
            modal_schur_comparison = {
                "status": ("pass" if all(comparison_gates.values()) else "failed"),
                "comparison_solver_path": comparison_solver_path,
                "comparison_solver_path_argument": (args.comparison_solver_path),
                "comparison_lifecycle_strategy": (schur_system.lifecycle_strategy),
                "multi_rhs_count": schur_system.multi_rhs_count,
                "modal_schur_shape": list(schur_system.modal_schur.shape),
                "modal_schur_bytes": int(schur_system.modal_schur.nbytes),
                "modal_schur_condition": schur_system.modal_schur_condition,
                "dense_interface_square_formed": (
                    schur_system.dense_interface_square_formed
                ),
                "full_field_or_mode_gathered": (
                    schur_system.full_field_or_mode_gathered
                ),
                "transient_dense_rhs_solution_bytes": (
                    schur_system.transient_dense_rhs_solution_bytes
                ),
                "factor_setup_seconds": schur_system.factor_setup_seconds,
                "multi_rhs_solve_seconds": schur_system.multi_rhs_solve_seconds,
                "modal_solve_seconds": schur_solution.modal_solve_seconds,
                "recovery_seconds": schur_solution.recovery_seconds,
                "residuals": {
                    "combined_relative": schur_solution.relative_residual,
                    "bottom_relative": schur_solution.bottom_relative_residual,
                    "top_relative": schur_solution.top_relative_residual,
                    "modal_relative": schur_solution.modal_relative_residual,
                },
                "augmented_vs_schur": {
                    "modal_coefficients_relative_error": float(
                        np.linalg.norm(modal_difference) / modal_scale
                    ),
                    "bottom_solution_relative_error": _relative_vector_error(
                        schur_solution.bottom, solution.bottom
                    ),
                    "top_solution_relative_error": _relative_vector_error(
                        schur_solution.top, solution.top
                    ),
                    "interface_e_projection_combined_residual_delta": float(
                        schur_validation["interface_e_projection"][
                            "combined_relative_residual"
                        ]
                        - validation["interface_e_projection"][
                            "combined_relative_residual"
                        ]
                    ),
                    "RTA_delta": rta_delta,
                },
                "gates": comparison_gates,
                "memory_comparison_semantics": (
                    "Correctness runner retains augmented and Schur factors concurrently; "
                    "its process peak is not a standalone Schur memory measurement."
                ),
            }
            progress(
                f"Task32 Phase7: {comparison_solver_path} direct comparison complete"
            )
        pinned_reference_case = abs(args.incident_grazing_deg - 10.0) <= 1.0e-12 and (
            args.polarization_kind == "s" or args.full3d_reference is not None
        )
        explicit_reference = args.full3d_reference
        if explicit_reference is not None and not explicit_reference.is_absolute():
            explicit_reference = ROOT / explicit_reference
        reference_registry = (
            None
            if explicit_reference is None
            else {(args.degree, float(args.h_nm)): explicit_reference}
        )
        loaded_reference = (
            _load_case080_reference(
                args.degree,
                args.h_nm,
                reference_by_degree_and_h=reference_registry,
                polarization_kind=args.polarization_kind,
            )
            if pinned_reference_case
            else None
        )
        reference = (
            _reference_comparison(loaded_reference, port_power)
            if pinned_reference_case
            else None
        )
        reference_archive = (
            _reference_archive(loaded_reference) if pinned_reference_case else None
        )
        if reference_archive is not None:
            archive_path, reference_record_path, reference_record = reference_archive
            with np.load(archive_path) as archive:
                sample_x = np.asarray(archive["x_nm"], dtype=np.float64)
                sample_y = np.asarray(archive["y_nm"], dtype=np.float64)
                sample_z = np.asarray(archive["z_nm"], dtype=np.float64)
        else:
            sample_x = (
                cfg.x_min
                + (np.arange(40, dtype=np.float64) + 0.5) * cfg.period_x / 40.0
            )
            sample_y = (
                cfg.y_min
                + (np.arange(20, dtype=np.float64) + 0.5) * cfg.period_y / 20.0
            )
            sample_z = np.linspace(
                args.bottom_interface_nm,
                args.top_interface_nm,
                5,
                dtype=np.float64,
            )
        mark_stage("middle_plane_reconstruction")
        started = time.perf_counter()
        reconstructor = ModalFieldReconstructor(
            cfg,
            cross_section,
            spaces,
            positive,
            negative,
            bottom_z_nm=args.bottom_interface_nm,
            top_z_nm=args.top_interface_nm,
            propagation=coupling.propagation,
            positive_traction_beta_per_nm=(coupling.positive_traction_beta_per_nm),
            negative_traction_beta_per_nm=(coupling.negative_traction_beta_per_nm),
        )
        reconstruction_traction_betas = reconstructor.traction_beta_per_nm
        trace_modal_oracle = None
        if reference_archive is not None:
            mark_stage("full3d_trace_modal_oracle")
            trace_modal_oracle = reconstructor.full3d_trace_modal_oracle(archive_path)
            mark_stage("middle_plane_reconstruction")
        selected_planes = reconstructor.selected_planes(
            solution.modal_amplitudes,
            sample_x,
            sample_y,
            sample_z,
        )
        interface_samples = reconstructor.selected_planes(
            solution.modal_amplitudes,
            sample_x,
            sample_y,
            np.asarray(
                [args.bottom_interface_nm, args.top_interface_nm],
                dtype=np.float64,
            ),
        )
        interface_continuity = interface_field_continuity(
            cfg,
            bottom,
            top,
            solution.bottom_physical,
            solution.top_physical,
            interface_samples,
        )
        for side in ("bottom", "top"):
            interface_continuity[side]["traction_hcurl_dual"] = validation[
                "fe_modal_traction_equilibrium"
            ][f"{side}_dual"]
        absorption = hybrid_volume_absorption(
            cfg,
            bottom,
            top,
            solution.bottom_physical,
            solution.top_physical,
            reconstructor,
            solution.modal_amplitudes,
            incident_power=float(port_power["incident_power_code_units"]),
        )
        field_reference = None
        if reference_archive is not None:
            field_reference = compare_selected_planes_to_reference(
                selected_planes, archive_path
            )
            expected_reference_npz_sha256 = str(
                reference_record["artifacts"]["reference_npz_sha256"]
            ).lower()
            observed_reference_npz_sha256 = _sha256(archive_path)
            field_reference.update(
                {
                    "reference_npz_sha256_expected": expected_reference_npz_sha256,
                    "reference_npz_sha256_observed": observed_reference_npz_sha256,
                    "reference_record": _serialize_reference_path(
                        reference_record_path
                    ),
                    "reference_record_sha256": _sha256(reference_record_path),
                    "reference_record_source_commit_full_sha": str(
                        reference_record["metadata"]["commit_sha"]
                    ).lower(),
                    "reference_binding_verified": (
                        expected_reference_npz_sha256 == observed_reference_npz_sha256
                    ),
                }
            )
        absorption["R_plus_T_plus_A_volume"] = float(
            port_power["R_total"] + port_power["T_total"] + absorption["A_volume_total"]
        )
        absorption["energy_closure_error"] = float(
            absorption["R_plus_T_plus_A_volume"] - 1.0
        )
        absorption["hybrid_A_balance_minus_A_volume_total"] = float(
            port_power["A_balance"] - absorption["A_volume_total"]
        )
        if reference_archive is not None:
            absorption["full3d_A_volume_total"] = float(
                reference_record["results"]["A_volume_total"]
            )
            absorption["hybrid_minus_full3d_A_volume_total"] = float(
                absorption["A_volume_total"]
                - reference_record["results"]["A_volume_total"]
            )
        physical_fields = {
            "sample_payload_bytes": int(
                selected_planes.electric_V_per_m.nbytes
                + selected_planes.magnetic_A_per_m.nbytes
            ),
            "sample_grid_shape_z_y_x_component": list(
                selected_planes.electric_V_per_m.shape
            ),
            "full_middle_volume_reconstructed": False,
            "interface_continuity": interface_continuity,
            "full3d_trace_modal_oracle": trace_modal_oracle,
            "volume_absorption": absorption,
            "selected_plane_full3d_comparison": field_reference,
        }
        timings["physical_field_reconstruction"] = _max_elapsed(comm, started)
        progress(
            "Task32 Phase6: physical interface/absorption/selected-plane reconstruction complete"
        )
        mark_stage("record_and_release")
        directions_valid = (
            all(mode.direction == "forward" for mode in positive.modes)
            and all(mode.direction == "backward" for mode in negative.modes)
            and all(mode.passive_branch_valid for mode in positive.modes)
            and all(mode.passive_branch_valid for mode in negative.modes)
        )
        reciprocal_valid = len(pairs) == args.requested_modes and all(
            pair.opposite_direction and pair.passive_branches_valid for pair in pairs
        )
        forward_factors = np.asarray(
            coupling.propagation.forward.factors, dtype=np.complex128
        )
        backward_factors = np.asarray(
            coupling.propagation.backward.factors, dtype=np.complex128
        )
        finite_rta = all(
            np.isfinite(port_power[key])
            for key in ("R_total", "T_total", "A_balance", "R_plus_T")
        )
        gates = {
            "exact_requested_mode_count_delivered": (
                len(positive.modes) == args.requested_modes
                and len(negative.modes) == args.requested_modes
            ),
            "requested_forward_and_backward_passive_bases": directions_valid,
            "reciprocal_pairing_complete": reciprocal_valid,
            "biorthogonality_identity_error_le_1e-6": (
                max(positive.max_identity_error, negative.max_identity_error) <= 1.0e-6
            ),
            "right_and_left_qep_residuals_le_1e-8": (
                max(
                    *(
                        mode.right.polynomial_relative_residual
                        for mode in positive.modes
                    ),
                    *(
                        mode.right.polynomial_relative_residual
                        for mode in negative.modes
                    ),
                    *(
                        mode.left_polynomial_relative_residual
                        for mode in positive.modes
                    ),
                    *(
                        mode.left_polynomial_relative_residual
                        for mode in negative.modes
                    ),
                )
                <= 1.0e-8
            ),
            "stable_propagation_no_growing_factor": bool(
                max(
                    np.max(np.abs(forward_factors), initial=0.0),
                    np.max(np.abs(backward_factors), initial=0.0),
                )
                <= 1.0 + 1.0e-12
            ),
            "interface_e_projection_relative_residual_le_1e-8": (
                validation["interface_e_projection"]["combined_relative_residual"]
                <= 1.0e-8
            ),
            "fe_modal_traction_equilibrium_relative_residual_le_1e-8": (
                max(
                    validation["fe_modal_traction_equilibrium"][
                        "bottom_relative_residual"
                    ],
                    validation["fe_modal_traction_equilibrium"][
                        "top_relative_residual"
                    ],
                )
                <= 1.0e-8
            ),
            "external_port_rta_finite": finite_rta,
        }
        if args.task037b_h3_gate:
            gates.update(
                {
                    "h3_converged_reason_positive": solution.converged_reason > 0,
                    "h3_outer_iterations_le_3": solution.iterations <= 3,
                    "h3_true_global_residual_le_1e-10": (
                        solution.relative_residual <= 1.0e-10
                    ),
                    "h3_true_bottom_residual_le_1e-10": (
                        solution.block_relative_residuals["bottom"] <= 1.0e-10
                    ),
                    "h3_true_top_residual_le_1e-10": (
                        solution.block_relative_residuals["top"] <= 1.0e-10
                    ),
                    "h3_true_modal_residual_le_1e-10": (
                        solution.block_relative_residuals["modal"] <= 1.0e-10
                    ),
                    "h3_direct_solution_relative_error_le_1e-10": (
                        h3_solution_error <= 1.0e-10
                    ),
                    "h3_direct_modal_relative_error_le_1e-10": (
                        h3_modal_error <= 1.0e-10
                    ),
                    "h3_factors_released": bool(
                        h3_after_inventory["oracle_local_direct_factor_count"] == 0
                        and h3_preconditioner.factors_released
                    ),
                    "h3_candidate_global_A_not_materialized": (
                        not system.inventory["global_A_materialized"]
                    ),
                    "h3_candidate_external_C_D_zero": (
                        system.inventory["explicit_external_c_matrix_count"] == 0
                        and system.inventory["explicit_external_d_matrix_count"] == 0
                    ),
                    "h3_candidate_p6_direct_factor_count_zero": (
                        system.inventory["p6_direct_factor_count"] == 0
                    ),
                }
            )
        elif args.task037b_h4_gate:
            gates.update(
                {
                    "h4a_converged_reason_positive": solution.converged_reason > 0,
                    "h4a_outer_iterations_le_3": solution.iterations <= 3,
                    "h4a_reported_residual_finite": bool(
                        np.isfinite(solution.reported_relative_residual)
                    ),
                    "h4a_true_global_residual_le_1e-10": (
                        solution.relative_residual <= 1.0e-10
                    ),
                    "h4a_true_bottom_residual_le_1e-10": (
                        solution.block_relative_residuals["bottom"] <= 1.0e-10
                    ),
                    "h4a_true_top_residual_le_1e-10": (
                        solution.block_relative_residuals["top"] <= 1.0e-10
                    ),
                    "h4a_true_modal_residual_le_1e-10": (
                        solution.block_relative_residuals["modal"] <= 1.0e-10
                    ),
                    "h4a_direct_solution_relative_error_le_1e-10": (
                        h3_solution_error <= 1.0e-10
                    ),
                    "h4a_direct_modal_relative_error_le_1e-10": (
                        h3_modal_error <= 1.0e-10
                    ),
                    "h4a_factors_released": bool(
                        h3_before_inventory["oracle_local_direct_factor_count"] == 2
                        and h3_after_inventory["oracle_local_direct_factor_count"] == 0
                        and h3_after_inventory["bottom_factor_released"] is True
                        and h3_after_inventory["top_factor_released"] is True
                        and h3_preconditioner.factors_released
                    ),
                    "h4b_diagnostic_finite": bool(
                        h4b_finite and h4_diagnostic_finite
                    ),
                    "h4b_evidence_complete": bool(
                        h4_telemetry is not None
                        and h4b_before_inventory is not None
                        and h4b_after_inventory is not None
                    ),
                    "h4b_factors_released": bool(
                        h4b_after_inventory is not None
                        and h4b_before_inventory is not None
                        and h4b_before_inventory["oracle_local_direct_factor_count"] == 2
                        and h4b_after_inventory["oracle_local_direct_factor_count"] == 0
                        and h4b_after_inventory["bottom_factor_released"] is True
                        and h4b_after_inventory["top_factor_released"] is True
                    ),
                    "h4_candidate_operator_contract": bool(
                        system.inventory["matrix_type"] == "python"
                        and system.inventory["matrix_free"] is True
                        and system.inventory["global_A_materialized"] is False
                        and system.inventory["bottom_global_F_materialized"] is False
                        and system.inventory["top_global_F_materialized"] is False
                    ),
                    "h4_candidate_global_A_not_materialized": (
                        not system.inventory["global_A_materialized"]
                    ),
                    "h4_candidate_external_C_D_zero": (
                        system.inventory["explicit_external_c_matrix_count"] == 0
                        and system.inventory["explicit_external_d_matrix_count"] == 0
                    ),
                    "h4_candidate_p6_direct_factor_count_zero": (
                        system.inventory["p6_direct_factor_count"] == 0
                    ),
                }
            )
        else:
            gates.update(
                {
                    "monolithic_true_relative_residual_le_1e-9": (
                        solution.relative_residual <= 1.0e-9
                    ),
                    "primary_direct_true_relative_residual_le_1e-9": (
                        solution.relative_residual <= 1.0e-9
                    ),
                }
            )
        if solution.bottom_recovered is not None:
            if solution.top_recovered is None:
                raise RuntimeError(
                    "Hybrid static recovery completed on only one local side."
                )
            recovered_sides = (
                solution.bottom_recovered,
                solution.top_recovered,
            )
            gates.update(
                {
                    "condensed_full_operator_relative_residual_le_1e-9": (
                        max(
                            item.full_operator_residual[
                                "linear_system_relative_residual"
                            ]
                            for item in recovered_sides
                        )
                        <= 1.0e-9
                    ),
                    "condensed_eliminated_interior_max_residual_le_1e-9": (
                        max(
                            item.full_operator_residual[
                                "eliminated_cell_interior_max_abs_residual"
                            ]
                            for item in recovered_sides
                        )
                        <= 1.0e-9
                    ),
                    "condensed_full_surface_mode_matrix_not_retained": all(
                        not item.streaming_audit["full_surface_mode_matrix_retained"]
                        for item in recovered_sides
                    ),
                    "condensed_full_global_matrix_not_allocated": all(
                        not item.streaming_audit["full_global_matrix_allocated"]
                        for item in recovered_sides
                    ),
                }
            )
        if physical_fields is not None:
            interface_physical = physical_fields["interface_continuity"]
            absorption_physical = physical_fields["volume_absorption"]
            exact_traction_values = [
                interface_physical.get(side, {})
                .get("traction_hcurl_dual", {})
                .get("relative_dual")
                for side in ("bottom", "top")
            ]
            exact_traction_pass, _exact_traction_role = _exact_traction_gate(
                {}, exact_traction_values, 1.0e-8
            )
            gates.update(
                {
                    "sampled_interface_e_t_relative_l2_le_5e-3": (
                        max(
                            interface_physical[side]["electric_tangential"][
                                "relative_l2"
                            ]
                            for side in ("bottom", "top")
                        )
                        <= 5.0e-3
                    ),
                    "diagnostic_sampled_traction_density_l2_proxy_le_1e-2": (
                        max(
                            interface_physical[side]["traction_density_l2_proxy"][
                                "relative_l2"
                            ]
                            for side in ("bottom", "top")
                        )
                        <= 1.0e-2
                    ),
                    "assembled_interface_h_t_exact_dual_le_1e-8": (exact_traction_pass),
                    "volume_energy_closure_abs_le_1e-5": (
                        abs(absorption_physical["energy_closure_error"]) <= 1.0e-5
                    ),
                }
            )
            planes_physical = physical_fields["selected_plane_full3d_comparison"]
            if planes_physical is not None:
                gates.update(
                    {
                        "volume_absorption_full3d_abs_delta_le_1e-5": (
                            abs(
                                absorption_physical[
                                    "hybrid_minus_full3d_A_volume_total"
                                ]
                            )
                            <= 1.0e-5
                        ),
                        "middle_plane_e_relative_l2_le_5e-3": (
                            planes_physical["max_middle_plane_electric_relative_l2"]
                            <= 5.0e-3
                        ),
                        "middle_plane_h_relative_l2_le_5e-3": (
                            planes_physical["max_middle_plane_magnetic_relative_l2"]
                            <= 5.0e-3
                        ),
                    }
                )
        physical_gate_prefixes = (
            "sampled_interface_",
            "assembled_interface_",
            "volume_",
            "middle_plane_",
        )
        algebraic_chain_pass = all(
            value
            for key, value in gates.items()
            if not key.startswith(physical_gate_prefixes)
            and not key.startswith("diagnostic_")
        )
        integration_pass = _all_formal_true(gates)
        interface_closure_pass = bool(
            physical_fields is not None
            and gates.get(
                "interface_e_projection_relative_residual_le_1e-8",
                False,
            )
            and gates.get(
                "fe_modal_traction_equilibrium_relative_residual_le_1e-8",
                False,
            )
            and gates.get(
                "sampled_interface_e_t_relative_l2_le_5e-3",
                False,
            )
            and gates.get(
                "assembled_interface_h_t_exact_dual_le_1e-8",
                False,
            )
        )
        hybrid_p_status = hybrid_p_disposition(
            cfg.polarization_kind,
            full3d_physical_solution_exists=loaded_reference is not None,
            modal_rank_sufficient=None,
            interface_closure_pass=interface_closure_pass,
            diagnostic_projection_bug=False,
        )
        task033_physical_truncation_allowed = bool(
            not task33_variant or args.requested_modes >= 80
        )
        projection_stats = {
            "bottom": _petsc_matrix_stats(coupling.bottom.projection, assemble=False),
            "top": _petsc_matrix_stats(coupling.top.projection, assemble=False),
        }
        if args.task037b_h4_gate:
            factor_inventory = {
                "h4a_preconditioner_before": h3_before_inventory,
                "h4a_preconditioner_after": h3_after_inventory,
                "h4b_preconditioner_before": h4b_before_inventory,
                "h4b_preconditioner_after": h4b_after_inventory,
                "post_h4_direct_comparison": h3_direct_factor_inventory,
            }
        elif args.task037b_h3_gate:
            factor_inventory = {
                "h3_preconditioner_before": h3_before_inventory,
                "h3_preconditioner_after": h3_after_inventory,
                "post_h3_direct_comparison": h3_direct_factor_inventory,
            }
        else:
            factor_inventory = (
                {"augmented": _petsc_factor_inventory(solution.ksp)}
                if system is not None
                else primary_schur_system.factor_inventory
            )
        full_vector_size = int(positive.modes[0].right.right_full.getSize())
        reduced_vector_size = int(positive.modes[0].right.right_reduced.getSize())
        eigenvector_bytes = int(
            2
            * args.requested_modes
            * 2
            * (full_vector_size + reduced_vector_size)
            * np.dtype(PETSc.ScalarType).itemsize
        )
        active_column_counts = {
            "bottom": distributed_active_column_count(coupling.bottom.projection),
            "top": distributed_active_column_count(coupling.top.projection),
        }
        object_payload_ledger = {
            "scalar_bytes": int(np.dtype(PETSc.ScalarType).itemsize),
            "index_bytes": int(np.dtype(PETSc.IntType).itemsize),
            "interface_active_dofs": {
                side: result.global_count
                for side, result in active_column_counts.items()
            },
            "interface_active_column_count_diagnostics": {
                side: result.to_dict() for side, result in active_column_counts.items()
            },
            "mode_count_per_direction": args.requested_modes,
            "retained_right_left_eigenvector_bytes": eigenvector_bytes,
            "projection_matrix": projection_stats,
            "modal_schur_bytes": (
                int(h3_before_inventory["modal_schur_bytes"])
                if args.task037b_h3_gate or args.task037b_h4_gate
                else (
                    0
                    if primary_schur_system is None
                    else int(primary_schur_system.modal_schur.nbytes)
                )
            ),
            "local_or_augmented_factor_inventory": factor_inventory,
            "storage_complexity_contract": "O(N_interface*M)+O(M^2)",
            "dense_interface_square_formed": False,
        }
        if args.task037b_h1_gate:
            if solution.bottom_recovered is None or solution.top_recovered is None:
                raise RuntimeError(
                    "Task037b H1 requires bottom and top static recovery."
                )
            bottom_recovery_seconds = float(
                solution.bottom_recovered.streaming_audit["total_seconds_max"]
            )
            top_recovery_seconds = float(
                solution.top_recovered.streaming_audit["total_seconds_max"]
            )
            h1_telemetry = {
                "task037b_h1_gate": True,
                "row_counts": {
                    "bottom_active_fe": int(bottom.n_fe),
                    "top_active_fe": int(top.n_fe),
                    "bottom_external_auxiliary": int(bottom.n_external_aux),
                    "top_external_auxiliary": int(top.n_external_aux),
                    "modal": int(coupling.internal_unknown_count),
                    "monolithic": int(system.layout.global_size),
                },
                "modal_amplitudes": _h1_replicated_array_digest(
                    solution.modal_amplitudes
                ),
                "bottom_condensed": _h1_owned_vec_digest(solution.bottom),
                "top_condensed": _h1_owned_vec_digest(solution.top),
                "bottom_recovered_full_fe": _h1_owned_vec_digest(
                    solution.bottom_recovered.electric_field.x.petsc_vec
                ),
                "top_recovered_full_fe": _h1_owned_vec_digest(
                    solution.top_recovered.electric_field.x.petsc_vec
                ),
                "rta_wall_seconds": timings["rta_evaluation"],
                "recovery_wall_seconds": {
                    "bottom": bottom_recovery_seconds,
                    "top": top_recovery_seconds,
                    "sequential_sum": (bottom_recovery_seconds + top_recovery_seconds),
                },
            }
        if args.task037b_h3_gate:
            h3_telemetry = {
                "task037b_h3_gate": True,
                "operator_inventory": system.inventory,
                "preconditioner_before": h3_before_inventory,
                "preconditioner_after": h3_after_inventory,
                "post_h3_direct_factor_inventory": h3_direct_factor_inventory,
                "outer_iterations": int(solution.iterations),
                "converged_reason": int(solution.converged_reason),
                "reported_relative_residual": float(
                    solution.reported_relative_residual
                ),
                "true_relative_residual": float(solution.relative_residual),
                "block_relative_residuals": solution.block_relative_residuals,
                "direct_solution_relative_error": float(h3_solution_error),
                "direct_modal_relative_error": float(h3_modal_error),
                "factorization_released": bool(h3_preconditioner.factors_released),
                "timings": {
                    key: timings[key]
                    for key in (
                        "oracle_local_matrix_build",
                        "h2b_action_assembly",
                        "h3_local_factor_setup",
                        "h3_outer_solve",
                        "post_h3_direct_comparison",
                        "rta_evaluation",
                        "recovery_rta",
                    )
                    if key in timings
                },
            }
        if args.task037b_h4_gate:
            h4_telemetry["operator_inventory"] = system.inventory
            h4_telemetry["post_h4_direct_factor_inventory"] = (
                h3_direct_factor_inventory
            )
            h4_telemetry["timings"].update(
                {
                    key: timings[key]
                    for key in (
                        "oracle_local_matrix_build",
                        "h2b_action_assembly",
                        "h3_local_factor_setup",
                        "h3_outer_solve",
                        "h3_factors_released",
                        "post_h3_direct_comparison",
                        "rta_evaluation",
                        "recovery_rta",
                    )
                    if key in timings
                }
            )
        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        rss = comm.gather(_historical_peak_rss_mb(), root=0)
        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "schema_version": 1,
            "benchmark_id": (
                "task037b_h4_bounded_modal_block_diagnostic"
                if args.task037b_h4_gate
                else (
                    "task037b_h3_exact_block_ldu_iterative_oracle"
                    if args.task037b_h3_gate
                    else (
                        "task032_phase6_hybrid_augmented_direct"
                        if args.degree == 2
                        and args.bottom_interface_nm == 10.0
                        and args.top_interface_nm == 110.0
                        and args.solver_path == "augmented"
                        else (
                            "task032_phase10_hybrid_modal_schur_direct"
                            if args.degree == 2
                            and args.bottom_interface_nm == 10.0
                            and args.top_interface_nm == 110.0
                            else "task033_high_order_or_buffer_hybrid_direct"
                        )
                    )
                )
            ),
            "timestamp_utc": timestamp,
            "status": (
                "task037b_h4_diagnostic_complete"
                if args.task037b_h4_gate and integration_pass
                else (
                    "task037b_h4_diagnostic_failed"
                    if args.task037b_h4_gate
                    else (
                        "task037b_h3_runner_gate_pass_12_channel_pending"
                        if args.task037b_h3_gate and integration_pass
                        else (
                            "HYBRID_BLOCK_ITERATIVE_ALGEBRA_FAILED"
                            if args.task037b_h3_gate
                            else (
                                "algebraic_smoke_pass_physical_truncation_not_qualified"
                                if task33_variant
                                and algebraic_chain_pass
                                and not task033_physical_truncation_allowed
                                else (
                                    "physical_integration_pass_mode_convergence_pending"
                                    if integration_pass
                                    else "physical_integration_failed"
                                )
                            )
                        )
                    )
                )
            ),
            "metadata": {
                **provenance,
                "timestamp_utc": timestamp,
                "command": "python -m benchmarks.run_task032_phase6_augmented "
                + " ".join(shlex.quote(value) for value in sys.argv[1:]),
                "mpi_size": comm.size,
                "container_image": args.container_image,
                "container_digest": args.container_digest,
                "host_environment_id": args.host_environment_id,
                "scalar_dtype": str(np.dtype(PETSc.ScalarType)),
                "full_field_or_mode_vector_gather": False,
                "primary_solver_path": args.solver_path,
                "internal_propagation_model_requested": (
                    args.internal_propagation_model
                ),
                "internal_traction_model_requested": (args.internal_traction_model),
                "stage4_full3d_assembly_backend_requested": (
                    args.stage4_full3d_assembly_backend
                ),
                "task035c_p6_h10_authority_gate": task035c_p6_gate,
                "task33_variant": task33_variant,
                "provenance": (
                    (
                        "clean_task033_high_order_or_buffer_hybrid_integration"
                        if task33_variant
                        else "clean_task032_phase6_real_qep_hybrid_integration"
                    )
                    if not provenance["tracked_source_dirty"]
                    else (
                        "dirty_task033_high_order_or_buffer_hybrid_research"
                        if task33_variant
                        else "dirty_task032_phase6_real_qep_hybrid_research"
                    )
                ),
            },
            "case": {
                "material_kind": "stage4_xy",
                "degree": args.degree,
                "h_nm": args.h_nm,
                "modal_degree": modal_degree,
                "modal_h_nm": modal_h_nm,
                "internal_propagation_model": (args.internal_propagation_model),
                "internal_traction_model": args.internal_traction_model,
                "discrete_axial_qualification_scope": (
                    _discrete_axial_qualification_scope(
                        args.internal_propagation_model,
                        args.internal_traction_model,
                    )
                ),
                "requested_modes_per_direction": args.requested_modes,
                "candidate_modes_per_target_branch": candidate_modes,
                "near_degenerate_tolerance": args.near_degenerate_tolerance,
                "block_rotation_tolerance": args.block_rotation_tolerance,
                "bottom_interface_nm": args.bottom_interface_nm,
                "top_interface_nm": args.top_interface_nm,
                "middle_length_nm": (args.top_interface_nm - args.bottom_interface_nm),
                "wavelength_nm": cfg.lambda0,
                "incident_grazing_deg": 90.0 - cfg.incident_theta_deg,
                "polarization_kind": cfg.polarization_kind,
                "mesh_policy": (
                    "task034_periodic_conforming_fixed_p_graded_opt_in"
                    if graded_plan is not None
                    else "reviewed_stage4_axis_plan"
                ),
                "graded_reference_h_nm": args.graded_reference_h,
                "graded_profile": (
                    args.graded_profile if graded_plan is not None else None
                ),
                "graded_coarse_factor": (
                    args.graded_coarse_factor if graded_plan is not None else None
                ),
                "graded_plan_hash": (
                    graded_plan.plan_hash if graded_plan is not None else None
                ),
                "graded_plan": (
                    graded_plan.to_record() if graded_plan is not None else None
                ),
            },
            "qep": {
                "target_beta_per_nm": _complex_json(target),
                "full_shape": list(operators.full_shape),
                "reduced_shape": list(operators.reduced_shape),
                "field_degree": operators.field_degree,
                "geometry_degree": operators.geometry_degree,
                "coefficient_degree": operators.coefficient_degree,
                "quadrature_degree": operators.quadrature_degree,
                "quadrature_policy": operators.quadrature_policy,
                "positive_solver_converged_modes": (positive_report.converged_modes),
                "negative_solver_converged_modes": (negative_report.converged_modes),
                "positive_directional_selection": (
                    _directional_selection_summary(positive_selection)
                ),
                "negative_directional_selection": (
                    _directional_selection_summary(negative_selection)
                ),
                "positive": _basis_summary(positive),
                "negative": _basis_summary(negative),
                "reciprocal_pairs": [
                    {
                        "positive_index": pair.positive_index,
                        "negative_index": pair.negative_index,
                        "relative_beta_error": pair.relative_beta_error,
                        "electric_mass_overlap": pair.electric_mass_overlap,
                        "opposite_direction": pair.opposite_direction,
                        "passive_branches_valid": (pair.passive_branches_valid),
                    }
                    for pair in pairs
                ],
            },
            "hybrid_system": {
                "primary_solver_path": args.solver_path,
                "operator_inventory": (
                    system.inventory
                    if (
                        args.task037b_h3_gate or args.task037b_h4_gate
                    ) and system is not None
                    else None
                ),
                "matrix_size": (
                    list(system.A.getSize()) if system is not None else None
                ),
                "matrix_stats": (system.matrix_stats if system is not None else None),
                "block_shapes": (system.block_shapes if system is not None else None),
                "inserted_nnz_by_block": (
                    system.inserted_nnz_by_block if system is not None else None
                ),
                "bottom_global_size": bottom.global_size,
                "top_global_size": top.global_size,
                "assembly_backend_requested": (args.stage4_full3d_assembly_backend),
                "bottom_assembly_backend_actual": (bottom.assembly_backend_actual),
                "top_assembly_backend_actual": top.assembly_backend_actual,
                "bottom_assembly_backend_qualification": (
                    bottom.assembly_backend_qualification
                ),
                "top_assembly_backend_qualification": (
                    top.assembly_backend_qualification
                ),
                "bottom_static_condensation": (
                    bottom.static_condensation.metadata.to_dict()
                    if bottom.static_condensation is not None
                    else None
                ),
                "top_static_condensation": (
                    top.static_condensation.metadata.to_dict()
                    if top.static_condensation is not None
                    else None
                ),
                "bottom_local_fe_dofs": bottom.n_fe,
                "top_local_fe_dofs": top.n_fe,
                "bottom_local_mesh_cells": list(bottom.local_mesh.mesh_cells),
                "top_local_mesh_cells": list(top.local_mesh.mesh_cells),
                "bottom_local_thickness_nm": (
                    bottom.local_mesh.interface_z_nm - bottom.local_mesh.external_z_nm
                ),
                "top_local_thickness_nm": (
                    top.local_mesh.external_z_nm - top.local_mesh.interface_z_nm
                ),
                "bottom_matrix_stats": bottom.augmented_matrix_stats,
                "top_matrix_stats": top.augmented_matrix_stats,
                "internal_unknown_count": coupling.internal_unknown_count,
                "internal_propagation": {
                    "model": coupling.propagation.propagation_model,
                    "authority_boundary": (
                        "scalar_CG_axial_phase_oracle; final authority remains "
                        "the measured 12-channel/field/residual closure"
                    ),
                    "modal_magnetic_and_traction_symbol": (
                        coupling.modal_traction_model
                    ),
                    "field_reconstruction_magnetic_beta_source": (
                        reconstructor.traction_model
                    ),
                    "field_reconstruction_positive_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in reconstruction_traction_betas[0]
                    ],
                    "field_reconstruction_negative_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in reconstruction_traction_betas[1]
                    ],
                    "positive_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.positive_traction_beta_per_nm
                    ],
                    "negative_traction_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.negative_traction_beta_per_nm
                    ],
                    "axial_fem_degree": int(cfg.nedelec_degree),
                    "axial_h_nm": float(cfg.mesh_target_size),
                    "forward_original_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.propagation.forward.beta_per_nm
                    ],
                    "forward_effective_beta_per_nm": [
                        _complex_json(value)
                        for value in (
                            coupling.propagation.forward.effective_beta_per_nm
                        )
                    ],
                    "forward_phase_corrections_rad": list(
                        coupling.propagation.forward.phase_corrections_rad
                    ),
                    "forward_log_magnitude_corrections": list(
                        coupling.propagation.forward.log_magnitude_corrections
                    ),
                    "backward_original_beta_per_nm": [
                        _complex_json(value)
                        for value in coupling.propagation.backward.beta_per_nm
                    ],
                    "backward_effective_beta_per_nm": [
                        _complex_json(value)
                        for value in (
                            coupling.propagation.backward.effective_beta_per_nm
                        )
                    ],
                    "backward_phase_corrections_rad": list(
                        coupling.propagation.backward.phase_corrections_rad
                    ),
                    "backward_log_magnitude_corrections": list(
                        coupling.propagation.backward.log_magnitude_corrections
                    ),
                    "max_factor_magnitude": float(
                        coupling.propagation.max_factor_magnitude
                    ),
                    "passivity_valid": bool(coupling.propagation.passivity_valid),
                },
                "qep_to_interface_quadrature_degree": (
                    coupling.interface_quadrature_degree
                ),
                "cell_interior_modal_correction_norms": {
                    side: {
                        "positive_frobenius": float(
                            np.linalg.norm(block.positive_interior_correction)
                        ),
                        "negative_frobenius": float(
                            np.linalg.norm(block.negative_interior_correction)
                        ),
                        "modal_rhs_l2": float(
                            np.linalg.norm(block.modal_rhs_correction)
                        ),
                    }
                    for side, block in (
                        ("bottom", coupling.bottom),
                        ("top", coupling.top),
                    )
                },
                "tangential_surface_trace_only_audit": {
                    side: {
                        "verified": bool(block.tangential_surface_trace_only_verified),
                        "pairwise_interior_schur_evaluated": bool(
                            block.interior_modal_pairwise_schur_evaluated
                        ),
                        "mathematical_contract": (
                            "pure tangential ds coupling; H(curl) "
                            "cell-interior tangential trace is zero"
                        ),
                    }
                    for side, block in (
                        ("bottom", coupling.bottom),
                        ("top", coupling.top),
                    )
                },
                "full_surface_mode_vectors_retained": bool(
                    coupling.bottom.full_surface_mode_vectors_retained
                    or coupling.top.full_surface_mode_vectors_retained
                ),
                "dense_interface_square_formed": (
                    system.dense_interface_square_formed
                    if system is not None
                    else primary_schur_system.dense_interface_square_formed
                ),
                "full_field_or_mode_gathered": (coupling.full_field_or_mode_gathered),
                "modal_schur": (
                    None
                    if primary_schur_system is None
                    else {
                        "shape": list(primary_schur_system.modal_schur.shape),
                        "bytes": int(primary_schur_system.modal_schur.nbytes),
                        "condition": primary_schur_system.modal_schur_condition,
                        "multi_rhs_count": primary_schur_system.multi_rhs_count,
                        "transient_dense_rhs_solution_bytes": (
                            primary_schur_system.transient_dense_rhs_solution_bytes
                        ),
                        "factor_setup_seconds": (
                            primary_schur_system.factor_setup_seconds
                        ),
                        "multi_rhs_solve_seconds": (
                            primary_schur_system.multi_rhs_solve_seconds
                        ),
                        "lifecycle_strategy": (primary_schur_system.lifecycle_strategy),
                        "recovery_refactor_required": (
                            primary_schur_system.recovery_refactor_required
                        ),
                    }
                ),
            },
            "solve": {
                "factor_solver": solution.factor_solver,
                "converged_reason": solution.converged_reason,
                "true_relative_residual": solution.relative_residual,
                "setup_seconds": getattr(solution, "setup_seconds", None),
                "solve_seconds": getattr(solution, "solve_seconds", None),
                "modal_solve_seconds": getattr(solution, "modal_solve_seconds", None),
                "recovery_seconds": getattr(solution, "recovery_seconds", None),
                "recovery_factor_setup_seconds": getattr(
                    solution, "recovery_factor_setup_seconds", {}
                ),
                "bottom_static_recovery": (
                    None
                    if solution.bottom_recovered is None
                    else {
                        "recovery": (solution.bottom_recovered.recovery_audit),
                        "full_operator_residual": (
                            solution.bottom_recovered.full_operator_residual
                        ),
                        "streaming": (solution.bottom_recovered.streaming_audit),
                    }
                ),
                "top_static_recovery": (
                    None
                    if solution.top_recovered is None
                    else {
                        "recovery": solution.top_recovered.recovery_audit,
                        "full_operator_residual": (
                            solution.top_recovered.full_operator_residual
                        ),
                        "streaming": solution.top_recovered.streaming_audit,
                    }
                ),
            },
            "validation": validation,
            "physical_field_reconstruction": physical_fields,
            "modal_schur_comparison": modal_schur_comparison,
            "object_payload_ledger": object_payload_ledger,
            "full3d_reference_comparison": reference,
            "gates": gates,
            "qualification": {
                "integration_pass": integration_pass,
                "algebraic_chain_pass": algebraic_chain_pass,
                "task033_physical_truncation_allowed": (
                    task033_physical_truncation_allowed
                ),
                "task033_minimum_physical_modes_per_direction": (
                    80 if task33_variant else None
                ),
                "clean_source_integration_record": bool(
                    integration_pass
                    and task033_physical_truncation_allowed
                    and not provenance["tracked_source_dirty"]
                ),
                "physical_augmented_direct_pass": False,
                "mode_count_converged": False,
                "physical_field_gates_pass": bool(
                    physical_fields is not None
                    and all(
                        value
                        for key, value in gates.items()
                        if (
                            key.startswith("sampled_interface_")
                            or key.startswith("assembled_interface_")
                            or key.startswith("volume_")
                            or key.startswith("middle_plane_")
                        )
                        and not key.startswith("diagnostic_")
                    )
                ),
                "pointwise_h_jump_checked": physical_fields is not None,
                "pointwise_h_jump_role": "diagnostic_sampled_proxy_only",
                "exact_variational_conormal_dual_checked": bool(
                    physical_fields is not None
                    and all(
                        "traction_hcurl_dual"
                        in physical_fields["interface_continuity"][side]
                        for side in ("bottom", "top")
                    )
                ),
                "volume_absorption_reconstructed": physical_fields is not None,
                "selected_middle_planes_reconstructed": physical_fields is not None,
                "official_record": False,
                "h3_algebra_disposition": (
                    (
                        "runner_gate_pass_12_channel_pending"
                        if integration_pass
                        else "HYBRID_BLOCK_ITERATIVE_ALGEBRA_FAILED"
                    )
                )
                if args.task037b_h3_gate
                else None,
                "h3_12_channel_comparator": (
                    "offline_required_not_recomputed_in_runner"
                    if args.task037b_h3_gate
                    else None
                ),
                "hybrid_p_disposition": hybrid_p_status,
                "boundary": (
                    (
                        "H3 in-run algebraic and field gates measured; "
                        "12+12 channel comparator pending offline"
                    )
                    if args.task037b_h3_gate
                    else (
                        (
                            "real_QEP_internal_physical_chain; no pinned "
                            "degree-compatible Case080 full3D reference is registered; "
                            "requires an M funnel and a separate equal-accuracy comparison"
                        )
                        if loaded_reference is None
                        else (
                            "real_QEP_physical_field_chain with a degree-compatible "
                            "full3D reference; requires a wider M funnel before "
                            "official qualification"
                        )
                    )
                ),
            },
            "timing_seconds_max_rank": {
                **timings,
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": rss,
            "memory_semantics": (
                "per-rank ru_maxrss historical peaks; not simultaneous RSS"
            ),
        }
        if args.task037b_h1_gate:
            record["h1_telemetry"] = h1_telemetry
            record["qualification"]["task037b_h1_gate"] = True
        if args.task037b_h3_gate:
            record["h3_telemetry"] = h3_telemetry
            record["qualification"]["task037b_h3_gate"] = True
        if args.task037b_h4_gate:
            record["h4_telemetry"] = h4_telemetry
            record["qualification"].update(
                {
                    "task037b_h4_gate": True,
                    "h4_disposition": (
                        "diagnostic_complete"
                        if integration_pass
                        else "diagnostic_failed"
                    ),
                    "h4_12_channel_comparator": (
                        "not_required_for_h4_bounded_diagnostic"
                    ),
                    "boundary": (
                        "H4a exact S_m algebra and H4b G-only bounded diagnostic "
                        "measured; H4 does not require a 12+12 comparator"
                    ),
                }
            )
    except _H5QualificationStop as stop:
        record = stop.record
        h3_oracle_bottom = None
        h3_oracle_top = None
    except _ModalBasisCapacityStop:
        pass
    finally:
        if h3_direct_comparison_solution is not None:
            h3_direct_comparison_solution.destroy()
        if h3_direct_comparison_system is not None:
            h3_direct_comparison_system.destroy()
        if h4b_solve_result is not None:
            h4b_solve_result.destroy()
        if h4b_preconditioner is not None:
            h4b_preconditioner.destroy()
        if h3_solve_result is not None:
            h3_solve_result.destroy()
        if h3_preconditioner is not None:
            h3_preconditioner.destroy()
        if h3_oracle_bottom is not None:
            h3_oracle_bottom.destroy()
        if h3_oracle_top is not None:
            h3_oracle_top.destroy()
        if h3_direct_bottom is not None:
            h3_direct_bottom.destroy()
        if h3_direct_top is not None:
            h3_direct_top.destroy()
        if h3_bottom_auxiliary_vec is not None:
            h3_bottom_auxiliary_vec.destroy()
        if h3_top_auxiliary_vec is not None:
            h3_top_auxiliary_vec.destroy()
        if h3_candidate_bottom is not None:
            h3_candidate_bottom.destroy()
        if h3_candidate_top is not None:
            h3_candidate_top.destroy()
        if schur_solution is not None:
            schur_solution.destroy()
        if schur_system is not None:
            schur_system.destroy()
        if solution is not None:
            solution.destroy()
        if primary_schur_system is not None:
            primary_schur_system.destroy()
        if system is not None:
            system.destroy()
        if coupling is not None:
            coupling.destroy()
        for local_system in (bottom, top):
            if local_system is not None:
                local_system.destroy()
        if positive is not None:
            positive.destroy()
        if negative is not None:
            negative.destroy()
        if operators is not None:
            operators.destroy()

    if comm.rank == 0:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, default=_json_default)
            + "\n",
            encoding="utf-8",
        )
        print(f"Task32 Phase6 record: {args.output}", flush=True)
        print(f"Task32 Phase6 status: {record['status']}", flush=True)
    comm.barrier()
    if not record["qualification"]["integration_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
