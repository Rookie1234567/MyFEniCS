from __future__ import annotations

import argparse
from contextlib import contextmanager
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
    HybridBlockLduDirectAction,
    HybridBlockLduPhysicalSolution,
    _HybridBlockLduOracleLocalSystem,
    action_block_screen_gate,
    action_block_v3_progressive_gate,
    create_action_block_ldu_preconditioner,
    create_exact_block_ldu_preconditioner,
    create_g_only_block_ldu_preconditioner,
    modal_block_diagnostic,
    multimetric_true_residual_decision,
    screen_action_block_ldu,
    solve_action_block_ldu_full,
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
    H5_MAX_IT,
    R3_PRECONDITIONER_PROFILE,
    build_hybrid_whole_endcap_fixed_smoother_action,
    build_hybrid_local_iterative_inverse,
)
from src.solvers.hybrid_local_dtn_action import (
    assemble_hybrid_local_dtn_action_system,
    create_hybrid_local_dtn_action_components,
)
from src.solvers.hybrid_local_dtn_woodbury import (
    R4_MODAL_COUNT,
    HybridLocalDtnWoodburyFixedAction,
    HybridLocalDtnWoodburyOracle,
    build_hybrid_local_dtn_woodbury_local_inverse,
)
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


def _array_descriptor(values: Any) -> dict[str, Any]:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.complex128))
    return {
        "shape": [int(value) for value in array.shape],
        "dtype": "complex128",
        "bytes": int(array.nbytes),
        "sha256": hashlib.sha256(array.tobytes(order="C")).hexdigest(),
    }


def _write_authority_grid_payload(
    path: Path,
    *,
    sample_x: np.ndarray,
    sample_y: np.ndarray,
    sample_z: np.ndarray,
    electric: np.ndarray,
    magnetic: np.ndarray,
    modal: np.ndarray,
    bottom_q: np.ndarray,
    top_q: np.ndarray,
    schema: str,
) -> dict[str, Any]:
    arrays = {
        "E_V_per_m": np.asarray(electric, dtype=np.complex128),
        "H_A_per_m": np.asarray(magnetic, dtype=np.complex128),
        "modal_amplitudes": np.asarray(modal, dtype=np.complex128),
        "bottom_q": np.asarray(bottom_q, dtype=np.complex128),
        "top_q": np.asarray(top_q, dtype=np.complex128),
    }
    expected_shapes = {
        "E_V_per_m": (5, 20, 40, 3),
        "H_A_per_m": (5, 20, 40, 3),
        "modal_amplitudes": (240,),
        "bottom_q": (40,),
        "top_q": (40,),
    }
    if any(
        value.shape != expected_shapes[name] or not np.all(np.isfinite(value))
        for name, value in arrays.items()
    ):
        raise RuntimeError("Authority payload has invalid shape or nonfinite values.")
    if (
        np.asarray(sample_x).shape != (40,)
        or np.asarray(sample_y).shape != (20,)
        or np.asarray(sample_z).shape != (5,)
    ):
        raise RuntimeError("Authority selected grid must be 5x20x40.")
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        x_nm=np.asarray(sample_x, dtype=np.float64),
        y_nm=np.asarray(sample_y, dtype=np.float64),
        z_nm=np.asarray(sample_z, dtype=np.float64),
        **arrays,
    )
    try:
        label = str(path.resolve().relative_to(ROOT))
    except ValueError:
        label = str(path.resolve())
    return {
        "path": label,
        "sha256": _sha256(path),
        "bytes": int(path.stat().st_size),
        "schema": schema,
        "rank0_only": True,
        "arrays": {name: _array_descriptor(value) for name, value in arrays.items()},
    }


@contextmanager
def _canonical_active_trace_view(source: PETSc.Vec, condensed: Any):
    """Expose only canonical active rows without copying an appended tail."""

    active_rows = int(condensed.active_rows)
    source_size = int(source.getSize())
    if source_size == active_rows:
        yield source
        return
    appended_rows = int(condensed.appended_rows)
    expected_size = active_rows + appended_rows
    if appended_rows <= 0 or source_size != expected_size:
        raise RuntimeError(
            "Canonical active source size must equal active rows or active plus "
            f"appended rows, got {source_size} for {active_rows}+{appended_rows}."
        )
    start, end = map(int, source.getOwnershipRange())
    local_n = max(0, min(end, active_rows) - start)
    active_is = PETSc.IS().createStride(
        local_n,
        first=start,
        step=1,
        comm=source.getComm(),
    )
    active_vec = source.getSubVector(active_is)
    try:
        yield active_vec
    finally:
        source.restoreSubVector(active_is, active_vec)
        active_is.destroy()


def _write_canonical_manifest_exports(
    *,
    systems: dict[str, Any],
    physical_solution: Any,
    run_dir: Path,
    comm: MPI.Intracomm,
    prefix: str,
) -> dict[str, Any]:
    from benchmarks.canonical_vector_artifacts import (
        MANIFEST_SCHEMA,
        canonical_shard_manifest,
        write_canonical_manifest,
        write_canonical_packet_shard,
    )
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        extract_canonical_active_trace_packets,
        extract_canonical_full_fe_packets,
    )

    if comm.rank == 0:
        run_dir.mkdir(parents=True, exist_ok=True)
    comm.barrier()
    try:
        run_dir_label = str(run_dir.resolve().relative_to(ROOT))
    except ValueError:
        run_dir_label = str(run_dir.resolve())
    exports: dict[str, Any] = {}
    for side in ("bottom", "top"):
        system = systems[side]
        active_solution = (
            physical_solution.bottom if side == "bottom" else physical_solution.top
        )
        recovered_field = (
            physical_solution.bottom_recovered
            if side == "bottom"
            else physical_solution.top_recovered
        )
        condensed = system.static_condensation.condensed
        side_exports: dict[str, Any] = {}
        for packet_role in ("active_trace", "full_fe"):
            if packet_role == "active_trace":
                with _canonical_active_trace_view(
                    active_solution, condensed
                ) as trace_solution:
                    packets, audit = extract_canonical_active_trace_packets(
                        condensed,
                        system.V,
                        system.floquet_data,
                        trace_solution,
                    )
            else:
                packets, audit = extract_canonical_full_fe_packets(
                    system.V,
                    recovered_field.electric_field.x.petsc_vec,
                    system.floquet_data,
                )
            packet_finite = bool(
                all(
                    np.isfinite(complex(value).real)
                    and np.isfinite(complex(value).imag)
                    for _key, value in packets
                )
            )
            if not packet_finite or int(audit["local_duplicate_count"]) != 0:
                raise RuntimeError(f"{side} {packet_role} canonical audit failed.")
            shard_path = run_dir / (
                f"{prefix}_{side}_{packet_role}_canonical_rank{comm.rank:04d}.jsonl"
            )
            shard = write_canonical_packet_shard(shard_path, packets)
            shard.update(
                {
                    "rank": int(comm.rank),
                    "local_duplicate_count": int(audit["local_duplicate_count"]),
                    "extractor_audit": audit,
                    "packet_finite": packet_finite,
                }
            )
            by_rank = comm.gather(shard, root=0)
            if comm.rank == 0:
                by_rank = sorted(by_rank, key=lambda item: int(item["rank"]))
                manifest = canonical_shard_manifest(
                    role=f"{side}_{packet_role}",
                    mpi_size=comm.size,
                    shard_metadata=by_rank,
                    extractor_audit={
                        "by_rank": [item["extractor_audit"] for item in by_rank]
                    },
                )
                manifest_path = run_dir / (
                    f"{prefix}_{side}_{packet_role}_canonical_manifest.json"
                )
                manifest_sha256 = write_canonical_manifest(manifest_path, manifest)
                extractor_global_count = int(
                    sum(
                        int(item["extractor_audit"]["local_packet_count"])
                        for item in by_rank
                    )
                )
                manifest_audit = manifest["extractor_audit"]["by_rank"]
                role_pass = bool(
                    all(item["packet_finite"] for item in by_rank)
                    and all(
                        int(item["extractor_audit"]["local_duplicate_count"]) == 0
                        for item in by_rank
                    )
                    and int(manifest["global_summed_packet_count"])
                    == extractor_global_count
                    and int(manifest["global_summed_packet_count"])
                    == int(
                        sum(int(item["local_packet_count"]) for item in manifest_audit)
                    )
                )
                try:
                    manifest_label = str(manifest_path.resolve().relative_to(ROOT))
                except ValueError:
                    manifest_label = str(manifest_path.resolve())
                side_exports[packet_role] = {
                    "manifest": manifest_label,
                    "manifest_sha256": manifest_sha256,
                    "schema_version": MANIFEST_SCHEMA,
                    "global_summed_packet_count": int(
                        manifest["global_summed_packet_count"]
                    ),
                    "extractor_global_packet_count": extractor_global_count,
                    "packet_finite": all(item["packet_finite"] for item in by_rank),
                    "local_duplicates_zero": all(
                        int(item["extractor_audit"]["local_duplicate_count"]) == 0
                        for item in by_rank
                    ),
                    "manifest_audit_count_matches": role_pass,
                    "pass": role_pass,
                }
            side_exports = comm.bcast(
                side_exports if comm.rank == 0 else None,
                root=0,
            )
            del packets
        exports[side] = {"run_directory": run_dir_label, "roles": side_exports}
    return exports


def _v5_snapshot_metadata(
    value: Any,
    *,
    comm: MPI.Intracomm,
    ownership: str,
) -> dict[str, Any]:
    """Record a layout-bound digest for one retained V5 solution snapshot."""

    if hasattr(value, "getOwnershipRange") and hasattr(value, "getArray"):
        vec_comm = value.getComm().tompi4py()
        local = np.ascontiguousarray(
            np.asarray(value.getArray(readonly=True), dtype=np.complex128)
        )
        local_size = int(local.size)
        local_sizes = [int(item) for item in vec_comm.allgather(local_size)]
        finite = bool(
            vec_comm.allreduce(
                bool(np.all(np.isfinite(local))),
                op=MPI.LAND,
            )
        )
        digest = _h1_owned_vec_digest(value)
        return {
            "shape": [int(value.getSize())],
            "global_size": int(value.getSize()),
            "local_size": local_size,
            "local_size_by_rank": local_sizes,
            "global_bytes": int(value.getSize()) * np.dtype(np.complex128).itemsize,
            "local_bytes": int(local.nbytes),
            "dtype": "complex128",
            "ownership": ownership,
            "finite": finite,
            "content_hash": digest["sha256"],
            "layout_digest": digest,
        }
    array = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
    finite = bool(
        comm.allreduce(
            bool(np.all(np.isfinite(array))),
            op=MPI.LAND,
        )
    )
    digest = _h1_replicated_array_digest(array)
    return {
        "shape": [int(item) for item in array.shape],
        "global_size": int(array.size),
        "local_size": int(array.size),
        "local_size_by_rank": [int(array.size)] * comm.size,
        "global_bytes": int(array.nbytes),
        "local_bytes": int(array.nbytes),
        "dtype": "complex128",
        "ownership": ownership,
        "finite": finite,
        "content_hash": digest["sha256"],
        "layout_digest": digest,
    }


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


class _V1QualificationStop(RuntimeError):
    """Internal control flow after writing the bounded V1-R1 record."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("status", "V1-R1 qualification complete"))
        self.record = record


class _V1R2QualificationStop(RuntimeError):
    """Internal control flow after writing the bounded V1-R2 record."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("status", "V1-R2 qualification complete"))
        self.record = record


class _V1R3QualificationStop(RuntimeError):
    """Internal control flow after writing the bounded V1-R3 record."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("status", "V1-R3 qualification complete"))
        self.record = record


class _V1R4QualificationStop(RuntimeError):
    """Internal control flow after the bounded V1-R4 record is complete."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("status", "V1-R4 qualification complete"))
        self.record = record


class _V1R5QualificationStop(RuntimeError):
    """Internal control flow after the bounded V1-R5 record is complete."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("status", "V1-R5 qualification complete"))
        self.record = record


class _V2QualificationStop(RuntimeError):
    """Internal control flow after one bounded V2 block-screen record."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("status", "V2 block screen complete"))
        self.record = record


class _V3QualificationStop(RuntimeError):
    """Internal control flow after the single bounded V3 double screen."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("status", "V3 double block screen complete"))
        self.record = record


class _V4QualificationStop(RuntimeError):
    """Internal control flow after the bounded V4 full-solve record."""

    def __init__(self, record: dict[str, Any]) -> None:
        super().__init__(record.get("status", "V4 full solve complete"))
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
        "--task037b-h1-authority-export",
        action="store_true",
        help="Opt in to the numeric H1 direct-Hybrid authority payload export.",
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
    parser.add_argument(
        "--task037b-v1-gate",
        action="store_true",
        help="Open only the frozen Task037b V1 DtN component-action path.",
    )
    parser.add_argument(
        "--task037b-v2-gate",
        action="store_true",
        help="Open only the frozen Task037b V2 bounded block-screen path.",
    )
    parser.add_argument(
        "--task037b-v3-gate",
        action="store_true",
        help="Open only the frozen Task037b V3 double fixed-action screen path.",
    )
    parser.add_argument(
        "--task037b-v4-gate",
        action="store_true",
        help="Open only the frozen Task037b V4 double fixed-action full-solve path.",
    )
    parser.add_argument(
        "--task037b-v5-gate",
        action="store_true",
        help=(
            "Open only the research-only Task037b V5 multimetric full-solve path; "
            "requires the frozen V4 gate."
        ),
    )
    parser.add_argument(
        "--task037b-v6-gate",
        action="store_true",
        help=(
            "Open only the research-only Task037b V6 traction-aligned full-solve "
            "path; requires the frozen V4 and V5 gates."
        ),
    )
    parser.add_argument(
        "--task037b-v2-profile",
        choices=("bottom-approx", "top-approx", "double"),
        default=None,
    )
    parser.add_argument(
        "--task037b-v2-max-it",
        choices=(20, 100, 200),
        type=int,
        default=None,
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
            "dtn-component-qualification",
            "f-only-local-inverse-qualification",
            "whole-endcap-ilu0-qualification",
            "dtn-woodbury-oracle-qualification",
            "dtn-woodbury-local-inverse-qualification",
            "block-ldu-action-screen",
            "block-ldu-action-full-solve",
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
        args.task037b_v1_gate,
        args.task037b_v2_gate,
        args.task037b_v3_gate,
        args.task037b_v4_gate,
    )
    if sum(bool(value) for value in selected_scoped_gates) > 1:
        parser.error(
            "Task035c p6/h10, Task037b H1, H3, H4, H5, V1, V2, V3, and V4 gates are "
            "mutually exclusive."
        )
    if args.task037b_v5_gate and not args.task037b_v4_gate:
        parser.error("--task037b-v5-gate requires --task037b-v4-gate.")
    if args.task037b_v6_gate and not args.task037b_v5_gate:
        parser.error("--task037b-v6-gate requires --task037b-v5-gate.")
    if args.task037b_v6_gate and not args.task037b_v4_gate:
        parser.error("--task037b-v6-gate requires --task037b-v4-gate.")
    if args.task037b_h1_authority_export and not args.task037b_h1_gate:
        parser.error("--task037b-h1-authority-export requires --task037b-h1-gate.")
    if args.solver_path == "local-inverse-qualification" and not args.task037b_h5_gate:
        parser.error("local-inverse-qualification requires --task037b-h5-gate.")
    if args.solver_path == "dtn-component-qualification" and not args.task037b_v1_gate:
        parser.error("dtn-component-qualification requires --task037b-v1-gate.")
    if (
        args.solver_path == "f-only-local-inverse-qualification"
        and not args.task037b_v1_gate
    ):
        parser.error("f-only-local-inverse-qualification requires --task037b-v1-gate.")
    if (
        args.solver_path == "whole-endcap-ilu0-qualification"
        and not args.task037b_v1_gate
    ):
        parser.error("whole-endcap-ilu0-qualification requires --task037b-v1-gate.")
    if (
        args.solver_path == "dtn-woodbury-oracle-qualification"
        and not args.task037b_v1_gate
    ):
        parser.error("dtn-woodbury-oracle-qualification requires --task037b-v1-gate.")
    if (
        args.solver_path == "dtn-woodbury-local-inverse-qualification"
        and not args.task037b_v1_gate
    ):
        parser.error(
            "dtn-woodbury-local-inverse-qualification requires --task037b-v1-gate."
        )
    if args.solver_path == "block-ldu-action-screen" and not (
        args.task037b_v2_gate or args.task037b_v3_gate
    ):
        parser.error(
            "block-ldu-action-screen requires --task037b-v2-gate or --task037b-v3-gate."
        )
    if args.solver_path == "block-ldu-action-full-solve" and not args.task037b_v4_gate:
        parser.error("block-ldu-action-full-solve requires --task037b-v4-gate.")
    if args.task037b_v2_gate and args.solver_path != "block-ldu-action-screen":
        parser.error(
            "--task037b-v2-gate requires --solver-path block-ldu-action-screen."
        )
    if args.task037b_v3_gate and args.solver_path != "block-ldu-action-screen":
        parser.error(
            "--task037b-v3-gate requires --solver-path block-ldu-action-screen."
        )
    if args.task037b_v4_gate and args.solver_path != "block-ldu-action-full-solve":
        parser.error(
            "--task037b-v4-gate requires --solver-path block-ldu-action-full-solve."
        )
    if args.task037b_v5_gate and args.solver_path != "block-ldu-action-full-solve":
        parser.error(
            "--task037b-v5-gate requires --solver-path block-ldu-action-full-solve."
        )
    if args.task037b_v6_gate and args.solver_path != "block-ldu-action-full-solve":
        parser.error(
            "--task037b-v6-gate requires --solver-path block-ldu-action-full-solve."
        )
    if not args.task037b_v2_gate and (
        args.task037b_v2_profile is not None or args.task037b_v2_max_it is not None
    ):
        parser.error("V2 profile/max-it require --task037b-v2-gate.")
    if args.task037b_v2_gate and (
        args.task037b_v2_profile is None or args.task037b_v2_max_it is None
    ):
        parser.error("V2 gate requires --task037b-v2-profile and --task037b-v2-max-it.")
    if (
        args.task037b_v2_gate
        and args.task037b_v2_profile != "double"
        and args.task037b_v2_max_it != 20
    ):
        parser.error("V2 one-sided profiles require --task037b-v2-max-it 20.")
    if args.task037b_v6_gate and (
        args.task037b_v2_profile is not None or args.task037b_v2_max_it is not None
    ):
        parser.error("V6 does not accept V2 profile/max-it options.")
    if args.degree == 6 and not any(selected_scoped_gates):
        parser.error(
            "p6 is fail-closed; pass a fixed scoped Task035c, Task037b H1, "
            "or Task037b H3/H4/H5/V1/V2/V3/V4 gate."
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
    elif args.task037b_v1_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path
            in (
                "dtn-component-qualification",
                "f-only-local-inverse-qualification",
                "whole-endcap-ilu0-qualification",
                "dtn-woodbury-oracle-qualification",
                "dtn-woodbury-local-inverse-qualification",
            )
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
                "--task037b-v1-gate is restricted to the fixed p6/h10, "
                "10/110 nm, S-polarized, full3d/scalar-CG, M120+M120, "
                "candidate240, dtn-component-qualification, "
                "f-only-local-inverse-qualification or "
                "whole-endcap-ilu0-qualification or "
                "dtn-woodbury-oracle-qualification, "
                "dtn-woodbury-local-inverse-qualification, "
                "static-condensed MPI8 path."
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
    elif args.task037b_v2_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "block-ldu-action-screen"
            and args.task037b_v2_profile in {"bottom-approx", "top-approx", "double"}
            and args.task037b_v2_max_it in {20, 100, 200}
            and (args.task037b_v2_profile == "double" or args.task037b_v2_max_it == 20)
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
                "--task037b-v2-gate is restricted to the fixed WSL p6/h10, "
                "10/110 nm, S-polarized, full3d/scalar-CG, M120+M120, "
                "candidate240, block-ldu-action-screen, static-condensed MPI8 "
                "path with a valid V2 profile/max-it pair."
            )
    elif args.task037b_v3_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "block-ldu-action-screen"
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
                "--task037b-v3-gate is restricted to the fixed WSL p6/h10, "
                "modal p6/h10, 10/110 nm, S-polarized, full3d/scalar-CG, "
                "M120+M120, candidate240, block-ldu-action-screen, "
                "static-condensed MPI8 path."
            )
    elif args.task037b_v4_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.modal_degree == 6
            and args.modal_h_nm is not None
            and math.isclose(args.modal_h_nm, 10.0)
            and args.requested_modes == 120
            and args.candidate_modes == 240
            and args.solver_path == "block-ldu-action-full-solve"
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
                "--task037b-v4-gate is restricted to the frozen p6/h10, modal "
                "p6/h10, 13.5 nm, S-polarized full3d/scalar-CG, 10/110 nm, "
                "M120/candidate240, block-ldu-action-full-solve, static-condensed "
                "MPI8 path."
            )
    elif (
        args.task035c_p6_preflight_authority is not None
        or args.task035c_p6_preflight_sha256 is not None
        or args.full3d_reference_sha256 is not None
    ):
        parser.error(
            "Task035c/H1/H3/H4/H5/V1/V2/V3/V4 authority SHA arguments require a scoped gate."
        )
    return args


def _v4_hash_bound_provenance_gate() -> dict[str, Any]:
    """Verify only hash-bound H1/V3 metadata before a V4 candidate run."""

    h1_records = {
        "solver_record": (
            ROOT
            / "benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8"
            / "solver_record.json",
            "290fc25c119bbf641b8f0277ed5f9a101bc11a4df898c9133509f53c56dd4a1c",
        ),
        "summary": (
            ROOT
            / "benchmarks/artifacts/task037b/h1_direct_authority_postfix_2990f35_mpi8.json",
            "e22aa1edfeab331d5a8be13ca085e029d5446a4fdf300a5787a00688ef700db2",
        ),
    }
    compact_path = (
        ROOT
        / "benchmarks/cases/101_hybrid_iterative_block_solver/records"
        / "task037b_v3_double_block_pc_screen_v1.json"
    )
    failures: list[str] = []
    observed: dict[str, Any] = {}
    for name, (path, expected) in h1_records.items():
        if not path.is_file():
            failures.append(f"missing_h1_{name}")
            continue
        actual = _sha256(path)
        observed[f"h1_{name}"] = {
            "path": path.relative_to(ROOT).as_posix(),
            "sha256": actual,
            "expected_sha256": expected,
        }
        if actual != expected:
            failures.append(f"h1_{name}_sha256_mismatch")
    compact: dict[str, Any] | None = None
    if not compact_path.is_file():
        failures.append("missing_v3_compact_record")
    else:
        compact_sha = _sha256(compact_path)
        observed["v3_compact"] = {
            "path": compact_path.relative_to(ROOT).as_posix(),
            "sha256": compact_sha,
            "expected_sha256": (
                "4b04bd54e17e12cff36e42f59f97af88d2296ce74e7b90eade3fedbd199cbee1"
            ),
        }
        if compact_sha != observed["v3_compact"]["expected_sha256"]:
            failures.append("v3_compact_sha256_mismatch")
        try:
            compact = json.loads(compact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append("v3_compact_unreadable")
        if not isinstance(compact, dict):
            failures.append("v3_compact_not_object")
    raw_artifacts = compact.get("raw_artifacts", {}) if compact else {}
    if not isinstance(raw_artifacts, dict):
        failures.append("v3_compact_raw_artifacts_missing")
        raw_artifacts = {}
    raw_observed: dict[str, Any] = {}
    for name, item in raw_artifacts.items():
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            failures.append(f"v3_raw_{name}_descriptor_missing")
            continue
        path = ROOT / item["path"]
        expected = item.get("sha256")
        if not path.is_file() or not isinstance(expected, str):
            failures.append(f"v3_raw_{name}_missing")
            continue
        actual = _sha256(path)
        raw_observed[name] = {
            "path": item["path"],
            "sha256": actual,
            "expected_sha256": expected,
        }
        if actual != expected:
            failures.append(f"v3_raw_{name}_sha256_mismatch")
    observed["v3_raw_artifacts"] = raw_observed
    return {
        "status": "pass" if not failures else "failed",
        "payload_loaded": False,
        "failures": failures,
        "observed": observed,
    }


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
        or args.task037b_v1_gate
        or args.task037b_v2_gate
        or args.task037b_v3_gate
        or args.task037b_v4_gate
    ):
        return None

    authority_path = args.task035c_p6_preflight_authority
    reference_path = args.full3d_reference
    if authority_path is None or reference_path is None:
        raise SystemExit(
            "Task035c/H1/H3/H4/H5/V1/V2/V3/V4 authority paths are required."
        )
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
            or args.task037b_v1_gate
            or args.task037b_v2_gate
            or args.task037b_v3_gate
            or args.task037b_v4_gate
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
    v4_provenance_gate = (
        _v4_hash_bound_provenance_gate() if args.task037b_v4_gate else None
    )
    gate = {
        "schema_version": (
            "task037b.h4-worker-authority-gate.v1"
            if args.task037b_h4_gate
            else "task037b.h3-worker-authority-gate.v1"
            if args.task037b_h3_gate
            else "task037b.v1-worker-authority-gate.v1"
            if args.task037b_v1_gate
            else "task037b.h5-worker-authority-gate.v1"
            if args.task037b_h5_gate
            else "task037b.v2-worker-authority-gate.v1"
            if args.task037b_v2_gate
            else "task037b.v3-worker-authority-gate.v1"
            if args.task037b_v3_gate
            else "task037b.v4-worker-authority-gate.v1"
            if args.task037b_v4_gate
            else "task035c.p6-h10-worker-authority-gate.v1"
        ),
        "pass": bool(
            preflight_gate["pass"]
            and reference_gate["pass"]
            and (v4_provenance_gate is None or v4_provenance_gate["status"] == "pass")
        ),
        "historical_preflight": {
            **preflight_gate,
            "path": str(authority_path),
        },
        "matching_full3d_reference": {
            **reference_gate,
            "path": str(reference_path),
        },
    }
    if v4_provenance_gate is not None:
        gate["v4_hash_bound_provenance"] = v4_provenance_gate
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
        *(
            []
            if v4_provenance_gate is None or v4_provenance_gate["status"] == "pass"
            else [
                f"v4_hash_bound_provenance:{failure}"
                for failure in v4_provenance_gate["failures"]
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


def _v2_not_run_validation_boundary() -> dict[str, Any]:
    """Return the fixed no-official-physics boundary for V2 records."""

    return {
        "official_record": False,
        "R": "not_run",
        "T": "not_run",
        "A": "not_run",
        "A_volume": "not_run",
        "orders": "not_run",
        "external_diffraction_orders": "not_run",
        "field": "not_run",
        "12_plus_12": "not_run",
        "Full3D": "not_run",
        "full3d_comparison": "not_run",
    }


def _v2_fixed_callback_certificate(
    action: HybridLocalDtnWoodburyFixedAction,
) -> dict[str, Any]:
    """Certify one fixed Woodbury callback without constructing another solver."""

    operator = action.operator
    source = operator.createVecRight()
    repeat_source = operator.createVecRight()
    combination = operator.createVecRight()
    wrapper = operator.createVecLeft()
    oracle = operator.createVecLeft()
    repeat_first = operator.createVecLeft()
    repeat_second = operator.createVecLeft()
    x = operator.createVecRight()
    y = operator.createVecRight()
    x_result = operator.createVecLeft()
    y_result = operator.createVecLeft()
    combination_result = operator.createVecLeft()
    expected = operator.createVecLeft()
    before = int(action.diagnostics["apply_count"])
    try:
        _h5_fill_partition_independent_random_rhs(source, 3701)
        source.copy(repeat_source)
        action.apply(source, wrapper)
        action.woodbury.apply(source, oracle)
        action.apply(repeat_source, repeat_first)
        action.apply(repeat_source, repeat_second)
        _h5_fill_partition_independent_random_rhs(x, 3702)
        _h5_fill_partition_independent_random_rhs(y, 3703)
        alpha = 0.37 - 0.11j
        beta = -0.23 + 0.19j
        x.copy(combination)
        combination.scale(PETSc.ScalarType(alpha))
        combination.axpy(PETSc.ScalarType(beta), y)
        action.apply(x, x_result)
        action.apply(y, y_result)
        x_result.copy(expected)
        expected.scale(PETSc.ScalarType(alpha))
        y_result.scale(PETSc.ScalarType(beta))
        expected.axpy(PETSc.ScalarType(1.0), y_result)
        action.apply(combination, combination_result)
        diagnostics = action.diagnostics
        woodbury = dict(diagnostics["woodbury"])
        base = dict(diagnostics["base_diagnostics"])
        repeat_error = _relative_vector_error(repeat_second, repeat_first)
        certificate = {
            "apply_count_before": before,
            "apply_count_after": int(diagnostics["apply_count"]),
            "apply_count_increment": int(diagnostics["apply_count"]) - before,
            "wrapper_vs_internal_woodbury_error": _relative_vector_error(
                wrapper, oracle
            ),
            "linearity_error": _relative_vector_error(combination_result, expected),
            "determinism_error": repeat_error,
            "repeat_hash_equal": bool(
                _h1_owned_vec_digest(repeat_first)["sha256"]
                == _h1_owned_vec_digest(repeat_second)["sha256"]
            ),
            "woodbury": woodbury,
            "base_diagnostics": base,
            "base_factor_count": int(diagnostics["base_factor_count"]),
            "local_direct_factor_count": int(diagnostics["local_direct_factor_count"]),
            "nested_ksp_created": bool(diagnostics["nested_ksp_created"]),
        }
        certificate["pass"] = bool(
            certificate["wrapper_vs_internal_woodbury_error"] <= 1.0e-13
            and certificate["linearity_error"] <= 1.0e-12
            and certificate["determinism_error"] <= 1.0e-14
            and certificate["repeat_hash_equal"]
            and woodbury.get("K_rank") == R4_MODAL_COUNT
            and np.isfinite(float(woodbury.get("K_condition_number")))
            and float(woodbury["K_condition_number"]) <= 1.0e10
            and woodbury.get("arrays_finite") is True
            and certificate["base_factor_count"] == 1
            and certificate["local_direct_factor_count"] == 0
            and certificate["nested_ksp_created"] is False
            and certificate["apply_count_increment"] == 7
        )
        return certificate
    finally:
        for vector in (
            expected,
            combination_result,
            y_result,
            x_result,
            y,
            x,
            repeat_second,
            repeat_first,
            oracle,
            wrapper,
            combination,
            repeat_source,
            source,
        ):
            vector.destroy()


def _v4_not_run_validation_boundary() -> dict[str, Any]:
    """Keep all official physics outputs closed until the full solve passes."""

    return {
        "official_record": "not_run",
        "R": "not_run",
        "T": "not_run",
        "A": "not_run",
        "A_volume": "not_run",
        "orders": "not_run",
        "external_diffraction_orders": "not_run",
        "field": "not_run",
        "12_plus_12": "not_run",
        "Full3D": "not_run",
        "full3d_comparison": "not_run",
        "candidate_sample_grid": "not_run",
        "canonical_export": "not_run",
    }


def _v4_full_fe_threshold_pass(
    full_relative: Any,
    interior_relative: Any,
    interior_max: Any,
    *,
    tight: bool = False,
) -> bool:
    """Apply the frozen V4 full-FE and interior recovery thresholds."""

    try:
        values = tuple(
            float(value)
            for value in (
                full_relative,
                interior_relative,
                interior_max,
            )
        )
    except (TypeError, ValueError):
        return False
    return bool(
        all(np.isfinite(value) and value >= 0.0 for value in values)
        and values[0] <= (1.0e-8 if tight else 1.0e-6)
        and values[1] <= (1.0e-10 if tight else 1.0e-8)
        and values[2] <= (1.0e-10 if tight else 1.0e-8)
    )


def _run_v4_full_solve(
    *,
    args: argparse.Namespace,
    comm: MPI.Intracomm,
    provenance: dict[str, Any],
    authority_gate: dict[str, Any] | None,
    cfg: Any,
    cross_section: Any,
    positive: Any,
    negative: Any,
    bottom: Any,
    top: Any,
    coupling: Any,
    timings: dict[str, float],
    total_started: float,
    mark_stage,
    v5_multimetric: bool = False,
    v6_traction_aligned: bool = False,
) -> None:
    """Run the single V4/V5 double fixed-action solve and controlled-stop record."""

    is_v6 = bool(v6_traction_aligned)
    v5_multimetric = bool(v5_multimetric or is_v6)
    profile_max_it = 1000 if is_v6 else 700
    profile_threshold = 5.0e-9 if is_v6 else 1.0e-6
    profile_identity = (
        "traction_aligned_multimetric_true_residual_gate"
        if is_v6
        else "multimetric_true_residual_gate"
    )

    layout = None
    action_matrix = None
    action_context = None
    outer_rhs = None
    preconditioner = None
    full_result = None
    physical_solution = None
    candidate_bottom = None
    candidate_top = None
    candidate_modal = None
    v5_snapshot_metadata: dict[str, Any] = {"status": "not_run"}
    v5_release_repeat: dict[str, Any] = {"status": "not_run"}
    v5_snapshot_release: dict[str, Any] = {"status": "not_run"}
    v5_multimetric_telemetry: dict[str, Any] | None = None
    v5_repeat_pass = True
    v5_snapshot_destroyed = False
    v5_bottom_snapshot_destroyed = False
    v5_top_snapshot_destroyed = False
    v5_modal_snapshot_released = False
    bottom_auxiliary_vec = None
    top_auxiliary_vec = None
    side_components: dict[str, Any] = {}
    side_fixed: dict[str, Any] = {}
    side_woodbury: dict[str, Any] = {}
    side_records: dict[str, dict[str, Any]] = {"bottom": {}, "top": {}}
    stage_markers: list[str] = []
    record: dict[str, Any] | None = None
    implementation_error: str | None = None
    recovery_error: str | None = None
    numerical_pass = False
    recovery_pass = False
    own_physics_pass = False
    physics_pass = False
    v5_implementation_pass = True
    external_recovery_pass = False
    full_fe_recovery_pass = False
    canonical_pass = False
    canonical_exports: dict[str, Any] = {}
    energy_pass = False
    direct_comparator: dict[str, Any] = {
        "status": "not_run",
        "pass": False,
    }
    recovery_gates: dict[str, Any] = {}
    release_ledger: dict[str, Any] = {}
    outer_release: dict[str, Any] = {}
    released = False
    validation: dict[str, Any] = _v4_not_run_validation_boundary()
    systems = {"bottom": bottom, "top": top}
    started = time.perf_counter()

    def record_stage(stage: str) -> None:
        mark_stage(stage)
        stage_markers.append(stage)

    def release_action_stack() -> None:
        nonlocal action_matrix, action_context, outer_rhs, preconditioner, released
        if released:
            return
        record_stage("release_started")
        deferred_modal_schur = bool(
            preconditioner is not None
            and getattr(preconditioner, "defer_action_modal_schur_release", False)
        )
        preconditioner_destroyed = False
        modal_schur_retained = False
        if preconditioner is not None:
            if not bool(getattr(preconditioner, "_destroyed", False)):
                preconditioner.destroy()
            preconditioner_destroyed = bool(
                getattr(preconditioner, "_destroyed", False)
            )
            if deferred_modal_schur:
                modal_schur_retained = bool(
                    preconditioner.inventory.get("modal_schur", {}).get("destroyed")
                    is False
                )
        outer_rhs_present = outer_rhs is not None
        outer_rhs_destroy_call_completed = False
        if outer_rhs is not None:
            outer_rhs.destroy()
            outer_rhs = None
            outer_rhs_destroy_call_completed = True
        release_order = ["pc_context"]
        release_objects = {
            side: {
                "fixed": side_fixed.pop(side, None),
                "woodbury": side_woodbury.pop(side, None),
                "components": side_components.pop(side, None),
            }
            for side in ("bottom", "top")
        }
        side_release: dict[str, Any] = {
            side: {"release_order": []}
            for side, objects in release_objects.items()
            if any(value is not None for value in objects.values())
        }
        for side in ("bottom", "top"):
            fixed = release_objects[side]["fixed"]
            if fixed is None:
                continue
            fixed.destroy()
            release_order.append(f"{side}_fixed_ilu")
            side_release[side]["release_order"].append(f"{side}_fixed_ilu")
            side_release[side]["fixed_base_after"] = dict(fixed.diagnostics)

        for side in ("bottom", "top"):
            woodbury = release_objects[side]["woodbury"]
            if woodbury is None:
                continue
            woodbury.destroy()
            release_order.append(f"{side}_woodbury_wklu")
            side_release[side]["release_order"].append(f"{side}_woodbury_wklu")
            side_release[side]["woodbury_after"] = dict(woodbury.diagnostics)

        modal_schur_release_call_completed = False
        modal_schur_released = False
        if preconditioner is not None and deferred_modal_schur:
            preconditioner.release_deferred_action_modal_schur()
            modal_schur_release_call_completed = True
            modal_schur_released = bool(
                preconditioner.inventory.get("modal_schur", {}).get("destroyed") is True
            )
            release_order.append("action_modal_schur")
        preconditioner = None

        for side in ("bottom", "top"):
            components = release_objects[side]["components"]
            if components is None:
                continue
            components.destroy()
            release_order.append(f"{side}_components")
            side_release[side]["release_order"].append(f"{side}_components")
            side_release[side]["components_destroyed"] = bool(
                getattr(components, "_destroyed", False)
            )

        for side, release_record in side_release.items():
            release_record.setdefault("fixed_base_after", None)
            release_record.setdefault("woodbury_after", None)
            release_record.setdefault("components_destroyed", False)
            release_record["release_pass"] = bool(
                release_record["woodbury_after"] is not None
                and release_record["woodbury_after"].get("destroyed") is True
                and release_record["fixed_base_after"] is not None
                and release_record["fixed_base_after"].get("destroyed") is True
                and release_record["components_destroyed"]
            )
            side_records[side]["release_records"] = release_record
        action_matrix_destroy_call_completed = False
        if action_matrix is not None:
            action_matrix.destroy()
            action_matrix = None
            action_matrix_destroy_call_completed = True
            release_order.append("outer_action_matrix")
        if action_context is not None:
            action_context.destroy()
            action_context_destroyed = bool(
                getattr(action_context, "_destroyed", False)
            )
            action_context = None
            release_order.append("outer_action_context")
        else:
            action_context_destroyed = False
        release_ledger.update(side_release)
        outer_release.update(
            {
                "preconditioner_destroyed": preconditioner_destroyed,
                "action_modal_schur_retained_after_pc_destroyed": (
                    modal_schur_retained
                ),
                "action_modal_schur_release_call_completed": (
                    modal_schur_release_call_completed
                ),
                "action_modal_schur_released": modal_schur_released,
                "outer_rhs_present": outer_rhs_present,
                "outer_rhs_destroy_call_completed": (outer_rhs_destroy_call_completed),
                "action_context_destroyed": action_context_destroyed,
                "action_matrix_destroy_call_completed": (
                    action_matrix_destroy_call_completed
                ),
                "release_order": release_order,
                "destroy_calls_complete": bool(
                    outer_rhs_destroy_call_completed
                    and action_matrix_destroy_call_completed
                    and action_context_destroyed
                ),
            }
        )
        released = True
        record_stage("release_finished")

    def mode_identity(system: Any) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        keys: list[tuple[Any, ...]] = []
        finite = True
        for mode in system.external_modes:
            beta = complex(mode.beta)
            row = {
                "m": int(mode.m),
                "n": int(mode.n),
                "beta": _complex_json(beta),
                "polarization": str(mode.polarization),
                "rayleigh_warning": bool(mode.rayleigh_warning),
            }
            rows.append(row)
            keys.append(
                (
                    row["m"],
                    row["n"],
                    row["polarization"],
                )
            )
            finite = bool(
                finite
                and row["polarization"] in {"s", "p"}
                and np.isfinite(beta.real)
                and np.isfinite(beta.imag)
            )
        return {
            "count": int(len(rows)),
            "rows": rows,
            "unique": len(set(keys)) == len(keys),
            "finite": finite,
            "pass": bool(
                len(rows) == R4_MODAL_COUNT and len(set(keys)) == len(keys) and finite
            ),
        }

    def external_q_identity(
        system: Any,
        active_solution: PETSc.Vec,
        amplitudes: np.ndarray,
    ) -> dict[str, Any]:
        values = np.asarray(amplitudes, dtype=np.complex128)
        q_vector = system.blocks.H.createVecRight()
        d_work = system.blocks.D.createVecLeft()
        h_work = system.blocks.H.createVecLeft()
        try:
            q_vector.set(PETSc.ScalarType(0.0))
            first, last = map(int, q_vector.getOwnershipRange())
            if last > first:
                q_vector.getArray()[:] = values[first:last]
            q_vector.assemble()
            system.blocks.D.mult(active_solution, d_work)
            system.blocks.H.mult(q_vector, h_work)
            d_values = _h3_replicated_vec_values(d_work)
            hq_values = _h3_replicated_vec_values(h_work)
            b_values = _h3_replicated_vec_values(system.blocks.b_aux)
        finally:
            q_vector.destroy()
            d_work.destroy()
            h_work.destroy()
        expected = b_values - d_values
        scale = max(
            float(np.linalg.norm(hq_values)),
            float(np.linalg.norm(expected)),
            1.0e-30,
        )
        residual = float(np.linalg.norm(hq_values - expected) / scale)
        finite = bool(
            values.shape == (len(system.external_modes),)
            and np.all(np.isfinite(values))
            and np.all(np.isfinite(hq_values))
            and np.all(np.isfinite(expected))
            and np.isfinite(residual)
        )
        return {
            "equation": "H*q - (b_aux - D*u)",
            "relative_residual": residual,
            "finite": finite,
            "pass": bool(finite and residual <= 1.0e-10),
        }

    def base_record() -> dict[str, Any]:
        return {
            "record_schema": (
                "task037b.v6-traction-aligned-full-block-pc.v1"
                if is_v6
                else "task037b.v5-multimetric-full-block-pc.v1"
                if v5_multimetric
                else "task037b.v4-full-block-pc.v1"
            ),
            "case": {
                "degree": int(args.degree),
                "h_nm": float(args.h_nm),
                "wavelength_nm": float(cfg.lambda0),
                "modal_degree": int(args.modal_degree),
                "modal_h_nm": float(args.modal_h_nm),
                "requested_modes": int(args.requested_modes),
                "candidate_modes": int(args.candidate_modes),
                "external_modes_per_endcap": int(R4_MODAL_COUNT),
                "interfaces_nm": [
                    float(args.bottom_interface_nm),
                    float(args.top_interface_nm),
                ],
                "grazing_deg": float(args.incident_grazing_deg),
                "polarization": args.polarization_kind,
                "propagation_model": args.internal_propagation_model,
                "traction_model": args.internal_traction_model,
                "assembly_backend": args.stage4_full3d_assembly_backend,
                "mpi_size": int(comm.size),
            },
            "solver": {
                "solver_path": "block-ldu-action-full-solve",
                "outer_solver": "right_fgmres",
                "restart": 90,
                "rtol": profile_threshold if v5_multimetric else 1.0e-6,
                "atol": 0.0,
                "max_it": profile_max_it if v5_multimetric else 700,
                "zero_initial": True,
                "normal_equations": False,
                "local_inverse_solve_called": False,
                "nested_ksp_created": False,
                "direct_fallback": False,
                **(
                    {"convergence_identity": profile_identity} if v5_multimetric else {}
                ),
            },
            "source": dict(provenance),
            "authority": dict(authority_gate or {}),
            "validation": dict(validation),
            "v4_telemetry": {
                "stage_markers": list(stage_markers),
                "official_outputs": dict(validation),
                "authority_payload_gap": "not_checked_in_candidate",
            },
            "qualification": {
                "integration_pass": False,
                "numerical_pass": False,
                "recovery_pass": False,
                "disposition": "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED",
            },
            "timing_seconds_max_rank": {},
        }

    try:
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
        outer_rhs = layout.pack(
            bottom.b,
            top.b,
            internal_modal_rhs_correction(coupling),
        )
        global_inventory = dict(action_context.inventory)
        global_direct = global_inventory.get("p6_direct_factor_count")
        global_contract = bool(
            global_direct is not None
            and int(global_direct) == 0
            and global_inventory.get("global_A_materialized") is False
            and global_inventory.get("matrix_free") is True
            and global_inventory.get("bottom_global_F_materialized") is False
            and global_inventory.get("top_global_F_materialized") is False
            and global_inventory.get("explicit_external_c_matrix_count") == 0
            and global_inventory.get("explicit_external_d_matrix_count") == 0
        )
        side_object_ledger = {}
        for side in ("bottom", "top"):
            system = systems[side]
            side_object_ledger[side] = {
                "action_system_inventory": dict(system.inventory),
                "base_matrix_stats": dict(system.base_matrix_stats),
                "augmented_matrix_stats": dict(system.augmented_matrix_stats),
                "coupling_stats": dict(system.coupling_stats),
                "static_condensation": system.static_condensation.metadata.to_dict(),
            }
            global_contract = bool(
                global_contract
                and system.inventory.get("fine_global_A_materialized") is False
                and system.inventory.get("explicit_external_c_matrix_count") == 0
                and system.inventory.get("explicit_external_d_matrix_count") == 0
            )
        record = base_record()
        record["hybrid_system"] = {
            "global_operator_inventory": global_inventory,
            "global_direct_factor_count": (
                None if global_direct is None else int(global_direct)
            ),
            "global_A_materialized": global_inventory.get("global_A_materialized"),
            "global_operator_contract": global_contract,
            "object_ledger": side_object_ledger,
        }
        if not global_contract:
            raise RuntimeError("V4 matrix-free/global-A contract failed.")

        for side in ("bottom", "top"):
            record_stage(f"{side}_approx_setup_started")
            components = create_hybrid_local_dtn_action_components(systems[side])
            side_components[side] = components
            fixed = build_hybrid_whole_endcap_fixed_smoother_action(systems[side])
            side_fixed[side] = fixed
            woodbury = HybridLocalDtnWoodburyFixedAction(fixed, components)
            side_woodbury[side] = woodbury
            side_records[side]["setup"] = {
                "operator_identity": woodbury.operator_identity,
                "base_identity": woodbury.diagnostics["base_identity"],
            }
            record_stage(f"{side}_approx_setup_ready")

        certificates: dict[str, dict[str, Any]] = {}
        callback_pass = True
        for side in ("bottom", "top"):
            certificate = _v2_fixed_callback_certificate(side_woodbury[side])
            certificates[side] = certificate
            woodbury = certificate["woodbury"]
            side_pass = bool(
                certificate["wrapper_vs_internal_woodbury_error"] <= 1.0e-12
                and certificate["linearity_error"] <= 1.0e-12
                and certificate["determinism_error"] <= 1.0e-14
                and certificate["repeat_hash_equal"]
                and woodbury.get("K_rank") == R4_MODAL_COUNT
                and np.isfinite(float(woodbury.get("K_condition_number")))
                and float(woodbury["K_condition_number"]) <= 1.0e6
                and woodbury.get("arrays_finite") is True
                and certificate["base_factor_count"] == 1
                and certificate["local_direct_factor_count"] == 0
                and certificate["nested_ksp_created"] is False
                and certificate["apply_count_increment"] == 7
            )
            side_records[side]["callback_certificate"] = certificate
            side_records[side]["callback_contract_pass"] = side_pass
            callback_pass = bool(callback_pass and side_pass)
        if not callback_pass:
            raise RuntimeError("V4 fixed callback certificate failed.")

        factor_identity = {}
        factor_identity_pass = True
        for side in ("bottom", "top"):
            diagnostics = dict(side_woodbury[side].diagnostics)
            direct = int(diagnostics.get("local_direct_factor_count", 0))
            ilu = int(diagnostics.get("base_factor_count", 0))
            item = {
                "direct_factor_count": direct,
                "ilu_factor_count": ilu,
                "borrowed_local_factor_count": direct + ilu,
                "expected_direct_factor_count": 0,
                "expected_ilu_factor_count": 1,
                "pass": bool(direct == 0 and ilu == 1),
            }
            factor_identity[side] = item
            side_records[side]["factor_identity"] = item
            factor_identity_pass = bool(factor_identity_pass and item["pass"])
        if not factor_identity_pass:
            raise RuntimeError("V4 side factor identity failed.")

        record_stage("modal_schur_build_started")
        preconditioner = create_action_block_ldu_preconditioner(
            layout,
            bottom,
            top,
            coupling,
            side_woodbury["bottom"],
            side_woodbury["top"],
        )
        pc_setup_inventory = dict(preconditioner.inventory)
        modal_diagnostics = dict(pc_setup_inventory.get("modal_schur", {}))
        pc_inventory_pass = bool(
            pc_setup_inventory.get("global_A_materialized") is False
            and pc_setup_inventory.get("borrowed_local_factor_count") == 2
            and pc_setup_inventory.get("pc_owned_local_factor_count") == 0
            and pc_setup_inventory.get("bottom_direct_factor_count") == 0
            and pc_setup_inventory.get("top_direct_factor_count") == 0
            and pc_setup_inventory.get("bottom_ilu_factor_count") == 1
            and pc_setup_inventory.get("top_ilu_factor_count") == 1
            and modal_diagnostics.get("shape") == [240, 240]
            and modal_diagnostics.get("dtype") == "complex128"
            and modal_diagnostics.get("rank") == 240
            and modal_diagnostics.get("finite") is True
            and np.isfinite(float(modal_diagnostics.get("condition")))
            and float(modal_diagnostics["condition"]) <= 1.0e8
            and modal_diagnostics.get("normal_equations") is False
            and float(modal_diagnostics.get("matrix_repeat_error")) <= 1.0e-12
            and float(modal_diagnostics.get("lu_repeat_solve_error")) <= 1.0e-12
            and all(
                int(value) == 480
                for value in modal_diagnostics.get("build_apply_count", {}).values()
            )
        )
        if not pc_inventory_pass:
            raise RuntimeError("V4 PC/modal Schur setup inventory failed.")
        record_stage("modal_schur_build_ready")
        online_before = {
            side: int(side_woodbury[side].diagnostics["apply_count"])
            for side in ("bottom", "top")
        }
        setup_elapsed = _max_elapsed(comm, started)
        timings["v4_setup"] = setup_elapsed

        checkpoint_iterations = {
            0,
            1,
            2,
            5,
            10,
            20,
            40,
            60,
            80,
            90,
            100,
            120,
            150,
            180,
            200,
            270,
            360,
            450,
            540,
            630,
            700,
        }
        if v5_multimetric:
            checkpoint_iterations.update({500, 520, 534, 550, 560, 580, 600})
        if is_v6:
            checkpoint_iterations.update(
                {
                    0,
                    1,
                    2,
                    5,
                    10,
                    20,
                    60,
                    100,
                    200,
                    500,
                    534,
                    557,
                    600,
                    630,
                    700,
                    750,
                    800,
                    850,
                    900,
                    950,
                    1000,
                }
            )

        def checkpoint_callback(row: dict[str, Any]) -> None:
            iteration = int(row["iteration"])
            if iteration in checkpoint_iterations:
                record_stage(f"outer_iter_{iteration}")

        outer_started = time.perf_counter()
        full_result = solve_action_block_ldu_full(
            action_matrix,
            outer_rhs,
            preconditioner,
            max_it=profile_max_it,
            checkpoint_callback=checkpoint_callback,
            v5_multimetric=v5_multimetric,
            v6_traction_aligned=is_v6,
        )
        timings["v4_outer_solve"] = _max_elapsed(comm, outer_started)
        solve_reason = int(full_result.converged_reason)
        v5_invalid_stop = bool(v5_multimetric and solve_reason == -9)
        solve_iterations = int(full_result.iterations)
        solve_reported = float(full_result.final_reported_relative_residual)
        solve_true = float(full_result.final_true_relative_residual)
        solve_blocks = dict(full_result.block_relative_residuals)
        v5_postsolve_audit = dict(full_result.postsolve_audit)
        solve_release = dict(full_result.release)
        solve_pc_seconds = float(full_result.pc_apply_seconds)
        online_after = {
            side: int(side_woodbury[side].diagnostics["apply_count"])
            for side in ("bottom", "top")
        }
        pc_count = int(full_result.inventory.get("pc_apply_count", 0))
        online = {}
        for side in ("bottom", "top"):
            increment = online_after[side] - online_before[side]
            online[side] = {
                "before": online_before[side],
                "after": online_after[side],
                "increment": increment,
                "expected_increment": 2 * pc_count,
                "pass": increment == 2 * pc_count,
            }
            side_records[side]["online_apply"] = online[side]
            side_records[side]["action_diagnostics_before_release"] = dict(
                side_woodbury[side].diagnostics
            )
            side_records[side]["borrowed_action_survives_after_solve"] = bool(
                not side_woodbury[side].diagnostics.get("destroyed", False)
            )
        history = [dict(row) for row in full_result.history]
        if v5_multimetric:
            history_final = history[-1]
            solve_reported = float(history_final["reported_relative_residual"])
            solve_true = float(history_final["global_true_relative_residual"])
            solve_blocks = {
                "bottom": float(history_final["bottom_true_relative_residual"]),
                "top": float(history_final["top_true_relative_residual"]),
                "modal": float(history_final["modal_true_relative_residual"]),
            }
            v5_residual_keys = (
                "reported_relative_residual",
                "global_true_relative_residual",
                "bottom_true_relative_residual",
                "top_true_relative_residual",
                "modal_true_relative_residual",
            )

            def v5_row_contract(row: dict[str, Any]) -> bool:
                decision_keys = (
                    "multimetric_max_true_residual",
                    "multimetric_decision",
                    "multimetric_reason",
                    "multimetric_identity",
                )
                if (
                    not isinstance(row.get("iteration"), int)
                    or isinstance(row.get("iteration"), bool)
                    or not all(key in row for key in decision_keys)
                    or not all(
                        isinstance(row.get(key), (int, float))
                        and not isinstance(row.get(key), bool)
                        for key in v5_residual_keys
                    )
                    or row["multimetric_identity"] != profile_identity
                ):
                    return False
                expected = multimetric_true_residual_decision(
                    int(row["iteration"]),
                    {key: row[key] for key in v5_residual_keys},
                    max_it=profile_max_it,
                    threshold=profile_threshold,
                    identity=profile_identity,
                )
                recorded_max = float(row["multimetric_max_true_residual"])
                expected_max = float(expected["max_true_residual"])
                max_matches = bool(
                    recorded_max == expected_max
                    or (math.isnan(recorded_max) and math.isnan(expected_max))
                )
                return bool(
                    max_matches
                    and row["multimetric_decision"] == expected["decision"]
                    and row["multimetric_reason"] == expected["reason"]
                )

            v5_implementation_pass = bool(
                [row.get("iteration") for row in history] == list(range(len(history)))
                and full_result.history_evaluation_count == len(history)
                and full_result.postsolve_evaluation_count == 1
                and all(v5_row_contract(row) for row in history)
            )
        residual_keys = (
            "global_true_relative_residual",
            "bottom_true_relative_residual",
            "top_true_relative_residual",
            "modal_true_relative_residual",
            "reported_relative_residual",
        )
        finite = bool(
            history
            and all(
                np.isfinite(float(row[key])) and float(row[key]) >= 0.0
                for row in history
                for key in residual_keys
            )
        )
        if v5_multimetric:
            v5_audit_values = {
                "reported_relative_residual": v5_postsolve_audit.get(
                    "ksp_reported_relative_residual"
                ),
                "global_true_relative_residual": v5_postsolve_audit.get(
                    "global_true_relative_residual"
                ),
                "bottom_true_relative_residual": v5_postsolve_audit.get(
                    "bottom_true_relative_residual"
                ),
                "top_true_relative_residual": v5_postsolve_audit.get(
                    "top_true_relative_residual"
                ),
                "modal_true_relative_residual": v5_postsolve_audit.get(
                    "modal_true_relative_residual"
                ),
            }
            v5_audit_finite = bool(
                all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and np.isfinite(float(value))
                    and float(value) >= 0.0
                    for value in v5_audit_values.values()
                )
            )
            numerical_pass = bool(
                solve_reason > 0
                and finite
                and solve_iterations <= profile_max_it
                and v5_audit_finite
                and v5_postsolve_audit.get("pass") is True
                and v5_implementation_pass
                and all(item["pass"] for item in online.values())
            )
        else:
            numerical_pass = bool(
                solve_reason > 0
                and finite
                and solve_iterations <= 700
                and solve_reported <= 1.0e-6
                and solve_true <= 1.0e-6
                and all(value <= 1.0e-6 for value in solve_blocks.values())
                and all(item["pass"] for item in online.values())
            )
        last90 = history[-90:] if history else []
        if v5_invalid_stop:
            last90_decrease = "not_applicable"
            last90_no_rebound = "not_applicable"
            last90_roundoff = "not_applicable"
        else:
            last90_decrease = bool(
                len(last90) >= 2
                and float(last90[-1]["global_true_relative_residual"])
                < float(last90[0]["global_true_relative_residual"])
            )
            last90_values = np.asarray(
                [float(row["global_true_relative_residual"]) for row in last90],
                dtype=np.float64,
            )
            last90_roundoff = (
                1024.0
                * np.finfo(np.float64).eps
                * max(float(np.max(np.abs(last90_values), initial=0.0)), 1.0e-30)
            )
            last90_no_rebound = bool(
                len(last90_values) >= 2
                and np.all(np.diff(last90_values) <= last90_roundoff)
            )
        slow_contraction = bool(
            not numerical_pass
            and solve_reason == -3
            and solve_iterations == 700
            and finite
            and last90_decrease
            and last90_no_rebound
        )
        v4_restart_local_rows = int(action_matrix.getLocalSize()[0])
        v4_restart_global_rows = int(action_matrix.getSize()[0])
        v4_restart_rows_by_rank = [
            int(value) for value in comm.allgather(v4_restart_local_rows)
        ]
        v4_restart_bytes_by_rank = [
            int((2 * 90 + 1) * rows * np.dtype(np.complex128).itemsize)
            for rows in v4_restart_rows_by_rank
        ]
        record["v4_telemetry"] = {
            "stage_markers": list(stage_markers),
            "history": history,
            "checkpoints": [dict(row) for row in full_result.checkpoints],
            "screen": {
                "converged_reason": solve_reason,
                "iterations": solve_iterations,
                "final_reported_relative_residual": solve_reported,
                "final_true_relative_residual": solve_true,
                "block_relative_residuals": solve_blocks,
                "finite": finite,
                "last90_net_decrease": last90_decrease,
                "last90_no_rebound": last90_no_rebound,
                "last90_roundoff_tolerance": last90_roundoff,
            },
            "fixed_callback": {
                "bottom": certificates["bottom"],
                "top": certificates["top"],
            },
            "pc_setup_inventory": pc_setup_inventory,
            "factor_identity": factor_identity,
            "online_apply": online,
            "modal_schur": modal_diagnostics,
            "pc_apply_count": pc_count,
            "pc_apply_seconds": solve_pc_seconds,
            "full_solve_release": solve_release,
            "restart_basis_bytes": {
                "derived_estimate": True,
                "formula": "(2*restart+1)*rows*complex128_bytes",
                "restart": 90,
                "local_rows": v4_restart_local_rows,
                "global_rows": v4_restart_global_rows,
                "local_bytes": int(
                    (2 * 90 + 1)
                    * v4_restart_local_rows
                    * np.dtype(np.complex128).itemsize
                ),
                "global_bytes": int(
                    (2 * 90 + 1)
                    * v4_restart_global_rows
                    * np.dtype(np.complex128).itemsize
                ),
                "rows_by_rank": v4_restart_rows_by_rank,
                "bytes_by_rank": v4_restart_bytes_by_rank,
                "sum_rows": int(sum(v4_restart_rows_by_rank)),
                "max_rows": int(max(v4_restart_rows_by_rank)),
                "sum_bytes": int(sum(v4_restart_bytes_by_rank)),
                "max_bytes": int(max(v4_restart_bytes_by_rank)),
            },
            "ordinary_default_changed": False,
            "official_outputs": dict(validation),
            "authority_payload_gap": "independent comparator requires numerical H1 arrays; not loaded",
        }
        if v5_multimetric:
            record["v4_telemetry"]["multimetric"] = {
                "identity": profile_identity,
                "profile": "v6_traction_aligned" if is_v6 else "v5_multimetric",
                "threshold": profile_threshold,
                "max_it": profile_max_it,
                "history_evaluation_count": int(full_result.history_evaluation_count),
                "postsolve_evaluation_count": int(
                    full_result.postsolve_evaluation_count
                ),
                "postsolve_audit": v5_postsolve_audit,
                "implementation_pass": v5_implementation_pass,
                ("v6_disposition" if is_v6 else "v5_disposition"): (
                    "V6_POSTSOLVE_PASS"
                    if is_v6 and numerical_pass
                    else "V5_POSTSOLVE_PASS"
                    if numerical_pass
                    else "CUSTOM_CONVERGENCE_FALSE_POSITIVE"
                    if v5_postsolve_audit.get("custom_convergence_false_positive")
                    else "TIGHT_LINEAR_GATE_NOT_REACHED_BY_1000"
                    if is_v6
                    and solve_reason == -3
                    and solve_iterations == profile_max_it
                    else "MULTIMETRIC_LINEAR_GATE_NOT_REACHED_BY_700"
                    if solve_reason == -3 and solve_iterations == 700
                    else "V5_MULTIMETRIC_NUMERICAL_NEGATIVE"
                ),
                "history_rows_have_decision_fields": bool(
                    all(
                        all(
                            key in row
                            for key in (
                                "multimetric_max_true_residual",
                                "multimetric_decision",
                                "multimetric_reason",
                                "multimetric_identity",
                            )
                        )
                        for row in history
                    )
                ),
            }
            v5_multimetric_telemetry = record["v4_telemetry"]["multimetric"]
        record["side_records"] = side_records

        if numerical_pass:
            candidate_bottom, candidate_top, candidate_modal = layout.split(
                full_result.solution,
                bottom.b,
                top.b,
            )
            if v5_multimetric:
                v5_snapshot_metadata = {
                    "status": "measured",
                    "full_solution": _v5_snapshot_metadata(
                        full_result.solution,
                        comm=comm,
                        ownership="PETSc.Vec retained full solution",
                    ),
                    "bottom_active": _v5_snapshot_metadata(
                        candidate_bottom,
                        comm=comm,
                        ownership="PETSc.Vec retained bottom active split",
                    ),
                    "top_active": _v5_snapshot_metadata(
                        candidate_top,
                        comm=comm,
                        ownership="PETSc.Vec retained top active split",
                    ),
                    "modal": _v5_snapshot_metadata(
                        candidate_modal,
                        comm=comm,
                        ownership="replicated retained modal amplitudes",
                    ),
                }
                v5_snapshot_metadata["pass"] = bool(
                    all(
                        item.get("finite") is True
                        for item in v5_snapshot_metadata.values()
                        if isinstance(item, dict)
                    )
                )
        if not v5_multimetric:
            full_result.destroy()
            full_result = None
        release_action_stack()
        record["v4_telemetry"]["release"] = {
            "sides": dict(release_ledger),
            "outer": dict(outer_release),
            "core_solve": solve_release,
        }
        side_release_pass = bool(
            all(
                release_ledger.get(side, {}).get("release_pass") is True
                for side in ("bottom", "top")
            )
        )
        outer_release_pass = bool(outer_release.get("destroy_calls_complete") is True)
        core_release_pass = bool(
            solve_release.get("ksp_destroyed") is True
            and solve_release.get("pc_context_destroyed") is True
            and solve_release.get("action_modal_schur_retained_after_pc_destroyed")
            is True
            and outer_release.get("action_modal_schur_retained_after_pc_destroyed")
            is True
            and outer_release.get("action_modal_schur_released") is True
            and solve_release.get("borrowed_side_actions_retained") is True
        )
        if v5_multimetric and numerical_pass:
            repeat_action = None
            repeat_context = None
            repeat_rhs = None
            repeat_residual = None
            repeat_mult_completed = False
            try:
                repeat_action, repeat_context = create_hybrid_assembled_block_action(
                    bottom,
                    top,
                    coupling,
                )
                repeat_rhs = layout.pack(
                    bottom.b,
                    top.b,
                    internal_modal_rhs_correction(coupling),
                )
                repeat_residual = repeat_action.createVecRight()
                repeat_action.mult(full_result.solution, repeat_residual)
                repeat_mult_completed = True
                repeat_residual.axpy(PETSc.ScalarType(-1.0), repeat_rhs)
                repeat_rhs_norm = max(float(repeat_rhs.norm()), 1.0e-30)
                repeat_global = float(repeat_residual.norm()) / repeat_rhs_norm
                pre_release_global = float(
                    v5_postsolve_audit["global_true_relative_residual"]
                )
                relative_difference = abs(repeat_global - pre_release_global) / max(
                    abs(repeat_global), abs(pre_release_global), 1.0e-30
                )
                repeat_inventory = dict(repeat_context.inventory)
                repeat_direct_counts = {
                    side: repeat_inventory.get(f"{side}_direct_factor_count")
                    for side in ("bottom", "top")
                }
                direct_counts_available = bool(
                    all(
                        isinstance(value, int)
                        and not isinstance(value, bool)
                        and value >= 0
                        for value in repeat_direct_counts.values()
                    )
                    and isinstance(repeat_inventory.get("p6_direct_factor_count"), int)
                    and not isinstance(
                        repeat_inventory.get("p6_direct_factor_count"), bool
                    )
                )
                measured_factor_count = (
                    int(sum(repeat_direct_counts.values()))
                    if direct_counts_available
                    else None
                )
                factor_inventory_consistent = bool(
                    direct_counts_available
                    and repeat_inventory["p6_direct_factor_count"]
                    == measured_factor_count
                )
                borrowed_actions_usable = bool(
                    repeat_mult_completed
                    and not bool(getattr(bottom, "_destroyed", False))
                    and not bool(getattr(top, "_destroyed", False))
                )
                v5_release_repeat = {
                    "status": "measured",
                    "pre_release_global_true_relative_residual": pre_release_global,
                    "post_release_global_true_relative_residual": repeat_global,
                    "relative_difference": relative_difference,
                    "finite": bool(
                        np.isfinite(pre_release_global)
                        and np.isfinite(repeat_global)
                        and np.isfinite(relative_difference)
                    ),
                    "borrowed_exact_actions_usable": borrowed_actions_usable,
                    "new_factor_count": measured_factor_count,
                    "factor_inventory": {
                        "bottom_direct_factor_count": repeat_direct_counts["bottom"],
                        "top_direct_factor_count": repeat_direct_counts["top"],
                        "p6_direct_factor_count": repeat_inventory.get(
                            "p6_direct_factor_count"
                        ),
                        "consistent": factor_inventory_consistent,
                    },
                    "new_factor_count_source": (
                        "repeat_context.inventory bottom/top/p6 direct factor counts"
                    ),
                    "new_ksp_count": 0,
                    "new_ksp_count_source": (
                        "create_hybrid_assembled_block_action MatPython path; "
                        "no KSP constructed"
                    ),
                    "direct_fallback": False,
                    "repeat_action_mult_completed": repeat_mult_completed,
                }
                v5_release_repeat["pass"] = bool(
                    v5_release_repeat["finite"]
                    and v5_release_repeat["relative_difference"] <= 1.0e-10
                    and borrowed_actions_usable
                    and factor_inventory_consistent
                    and v5_release_repeat["new_factor_count"] == 0
                    and v5_release_repeat["new_ksp_count"] == 0
                    and v5_release_repeat["direct_fallback"] is False
                )
            except Exception as exc:
                v5_release_repeat = {
                    "status": "failed",
                    "pass": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            finally:
                if repeat_residual is not None:
                    repeat_residual.destroy()
                if repeat_rhs is not None:
                    repeat_rhs.destroy()
                if repeat_action is not None:
                    repeat_action.destroy()
                if repeat_context is not None:
                    repeat_context.destroy()
            v5_repeat_pass = bool(v5_release_repeat.get("pass") is True)
        lifecycle_pass = bool(
            side_release_pass
            and outer_release_pass
            and core_release_pass
            and (not v5_multimetric or v5_repeat_pass)
        )
        record["v4_telemetry"]["release_pass"] = lifecycle_pass
        if v5_multimetric and v5_multimetric_telemetry is not None:
            v5_multimetric_telemetry["snapshot_metadata"] = v5_snapshot_metadata
            v5_multimetric_telemetry["release_repeat"] = v5_release_repeat
            v5_multimetric_telemetry["snapshot_release"] = v5_snapshot_release
        record["qualification"]["integration_pass"] = bool(
            global_contract
            and callback_pass
            and factor_identity_pass
            and pc_inventory_pass
            and (not v5_multimetric or v5_implementation_pass)
            and all(item["pass"] for item in online.values())
            and lifecycle_pass
        )
        if not record["qualification"]["integration_pass"]:
            raise RuntimeError(
                "V4 full-solve implementation/lifecycle contract failed."
            )
        if numerical_pass:
            record["v4_telemetry"]["recovery_phase"] = "external_auxiliary"
            record_stage("candidate_field_recovery")
            bottom_auxiliary_vec = recover_petsc_auxiliary(
                bottom.blocks,
                candidate_bottom,
            )
            top_auxiliary_vec = recover_petsc_auxiliary(top.blocks, candidate_top)
            bottom_auxiliary = _h3_replicated_vec_values(bottom_auxiliary_vec)
            top_auxiliary = _h3_replicated_vec_values(top_auxiliary_vec)
            external_gates: dict[str, Any] = {}
            for side, active_solution, amplitudes in (
                ("bottom", candidate_bottom, bottom_auxiliary),
                ("top", candidate_top, top_auxiliary),
            ):
                system = systems[side]
                external_gates[side] = {
                    "external_q_identity": external_q_identity(
                        system, active_solution, amplitudes
                    ),
                    "mode_identity": mode_identity(system),
                }
            external_recovery_pass = bool(
                all(
                    item["external_q_identity"].get("pass") is True
                    and item["mode_identity"].get("pass") is True
                    for item in external_gates.values()
                )
            )
            record["v4_telemetry"]["external_recovery_gates"] = external_gates
            record["v4_telemetry"]["recovery_phase"] = "full_fe"
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
            physical_solution = HybridBlockLduPhysicalSolution(
                bottom=candidate_bottom,
                top=candidate_top,
                modal_amplitudes=np.asarray(candidate_modal, dtype=np.complex128),
                bottom_auxiliary=bottom_auxiliary,
                top_auxiliary=top_auxiliary,
                bottom_recovered=bottom_recovered,
                top_recovered=top_recovered,
                factor_solver="fixed_dtn_woodbury_action",
                converged_reason=solve_reason,
                reported_relative_residual=solve_reported,
                relative_residual=solve_true,
                block_relative_residuals=solve_blocks,
                iterations=solve_iterations,
            )
            candidate_bottom = None
            candidate_top = None
            candidate_modal = None
            recovery_gates: dict[str, Any] = {}
            for side, recovered, active_solution, amplitudes in (
                (
                    "bottom",
                    physical_solution.bottom_recovered,
                    physical_solution.bottom,
                    bottom_auxiliary,
                ),
                (
                    "top",
                    physical_solution.top_recovered,
                    physical_solution.top,
                    top_auxiliary,
                ),
            ):
                system = systems[side]
                q_gate = external_gates[side]["external_q_identity"]
                mode_gate = external_gates[side]["mode_identity"]
                full_residual = dict(recovered.full_operator_residual)
                recovery_audit = dict(recovered.recovery_audit)
                streaming_audit = dict(recovered.streaming_audit)
                trace_audit = dict(
                    system.static_condensation.condensed.trace_constraints.build_audit
                )
                rhs_norm = max(
                    float(full_residual.get("linear_system_rhs_norm", 0.0)),
                    1.0e-30,
                )
                full_relative = float(
                    full_residual.get("linear_system_relative_residual", np.inf)
                )
                interior_relative = (
                    float(
                        full_residual.get(
                            "eliminated_cell_interior_residual_norm", np.inf
                        )
                    )
                    / rhs_norm
                )
                interior_max = float(
                    full_residual.get(
                        "eliminated_cell_interior_max_abs_residual", np.inf
                    )
                )
                trace_full_rows = int(trace_audit.get("full_trace_rows", -1))
                trace_active_rows = int(trace_audit.get("active_rows", -1))
                trace_slave_rows = int(trace_audit.get("slave_rows", -1))
                trace_contract_pass = bool(
                    trace_audit.get("status") == "exact_mpc_trace_expansion_built"
                    and trace_audit.get(
                        "constraint_applied_before_global_matrix_insertion"
                    )
                    is True
                    and trace_audit.get("embedded_identity_slave_rows_allocated")
                    is False
                )
                trace_rows_pass = bool(
                    trace_contract_pass
                    and trace_full_rows >= 0
                    and trace_active_rows >= 0
                    and trace_slave_rows >= 0
                    and trace_full_rows == trace_active_rows + trace_slave_rows
                    and trace_active_rows
                    == int(system.static_condensation.condensed.active_rows)
                    and trace_full_rows
                    == int(system.static_condensation.condensed.trace_rows)
                )
                full_finite = bool(
                    np.isfinite(full_relative)
                    and full_relative >= 0.0
                    and np.isfinite(interior_relative)
                    and interior_relative >= 0.0
                    and np.isfinite(interior_max)
                    and interior_max >= 0.0
                )
                recovery_audit_pass = bool(
                    recovery_audit.get("status")
                    == "full_field_recovered_without_full_global_matrix"
                    and recovery_audit.get("full_global_matrix_allocated") is False
                    and recovery_audit.get("full_trace_matrix_allocated") is False
                    and int(recovery_audit.get("recovered_interior_rows", -1))
                    == int(system.static_condensation.condensed.interior_rows)
                )
                streaming_pass = bool(
                    streaming_audit.get("full_surface_mode_matrix_retained") is False
                    and streaming_audit.get("full_global_matrix_allocated") is False
                    and streaming_audit.get("full_effective_rhs_reassembled_once")
                    is True
                )
                full_fe_pass = bool(
                    _v4_full_fe_threshold_pass(
                        full_relative,
                        interior_relative,
                        interior_max,
                        tight=is_v6,
                    )
                    and trace_rows_pass
                    and recovery_audit_pass
                    and streaming_pass
                )
                recovery_gates[side] = {
                    "external_q_identity": q_gate,
                    "mode_identity": mode_gate,
                    "full_operator_residual": full_residual,
                    "interior_relative_residual": interior_relative,
                    "interior_max_abs_residual": interior_max,
                    "trace_constraint_audit": trace_audit,
                    "trace_contract_pass": trace_contract_pass,
                    "trace_rows_pass": trace_rows_pass,
                    "full_finite": full_finite,
                    "recovery_audit": recovery_audit,
                    "streaming_audit": streaming_audit,
                    "recovery_audit_pass": recovery_audit_pass,
                    "streaming_pass": streaming_pass,
                    "full_fe_pass": full_fe_pass,
                    "pass": bool(q_gate["pass"] and mode_gate["pass"] and full_fe_pass),
                }
            external_recovery_pass = bool(
                all(
                    item.get("external_q_identity", {}).get("pass") is True
                    and item.get("mode_identity", {}).get("pass") is True
                    for item in recovery_gates.values()
                )
            )
            full_fe_recovery_pass = bool(
                all(
                    item.get("full_fe_pass") is True for item in recovery_gates.values()
                )
            )
            recovery_pass = bool(external_recovery_pass and full_fe_recovery_pass)
            record["v4_telemetry"]["recovery_gates"] = recovery_gates
            if external_recovery_pass and full_fe_recovery_pass:
                record["v4_telemetry"]["recovery_phase"] = "own_physics"
                validation_raw = evaluate_hybrid_augmented_solution(
                    cfg,
                    bottom,
                    top,
                    coupling,
                    physical_solution,
                    auxiliary_override=(bottom_auxiliary, top_auxiliary),
                )
                sample_x = (
                    cfg.x_min
                    + (np.arange(40, dtype=np.float64) + 0.5) * cfg.period_x / 40.0
                )
                sample_y = (
                    cfg.y_min
                    + (np.arange(20, dtype=np.float64) + 0.5) * cfg.period_y / 20.0
                )
                sample_z = np.asarray(
                    (10.0, 30.0, 60.0, 90.0, 110.0),
                    dtype=np.float64,
                )
                if tuple(sample_z.tolist()) != (10.0, 30.0, 60.0, 90.0, 110.0):
                    raise RuntimeError("V4 candidate planes are not frozen H1 planes.")
                reconstructor = ModalFieldReconstructor(
                    cfg,
                    cross_section,
                    coupling.spaces,
                    positive,
                    negative,
                    bottom_z_nm=args.bottom_interface_nm,
                    top_z_nm=args.top_interface_nm,
                    propagation=coupling.propagation,
                    positive_traction_beta_per_nm=(
                        coupling.positive_traction_beta_per_nm
                    ),
                    negative_traction_beta_per_nm=(
                        coupling.negative_traction_beta_per_nm
                    ),
                )
                selected_planes = reconstructor.selected_planes(
                    physical_solution.modal_amplitudes,
                    sample_x,
                    sample_y,
                    sample_z,
                )
                expected_grid_shape = (5, 20, 40, 3)
                if (
                    selected_planes.electric_V_per_m.shape != expected_grid_shape
                    or selected_planes.magnetic_A_per_m.shape != expected_grid_shape
                ):
                    raise RuntimeError(
                        "V4 own-grid E/H payload does not match 5x20x40x3."
                    )
                interface_samples = reconstructor.selected_planes(
                    physical_solution.modal_amplitudes,
                    sample_x,
                    sample_y,
                    np.asarray((10.0, 110.0), dtype=np.float64),
                )
                interface_continuity = interface_field_continuity(
                    cfg,
                    bottom,
                    top,
                    physical_solution.bottom_physical,
                    physical_solution.top_physical,
                    interface_samples,
                )
                absorption = hybrid_volume_absorption(
                    cfg,
                    bottom,
                    top,
                    physical_solution.bottom_physical,
                    physical_solution.top_physical,
                    reconstructor,
                    physical_solution.modal_amplitudes,
                    incident_power=float(
                        validation_raw["port_power"]["incident_power_code_units"]
                    ),
                )
                port_power = validation_raw["port_power"]
                r_value = float(port_power.get("R_total", np.nan))
                t_value = float(port_power.get("T_total", np.nan))
                a_value = float(port_power.get("A_balance", np.nan))
                a_volume = float(absorption.get("A_volume_total", np.nan))
                closure_error = float(r_value + t_value + a_volume - 1.0)
                balance_error = float(a_value - a_volume)
                traction = validation_raw["fe_modal_traction_equilibrium"]
                for side in ("bottom", "top"):
                    interface_continuity[side]["traction_hcurl_dual"] = traction[
                        f"{side}_dual"
                    ]
                traction_pass, traction_gate_role = _exact_traction_gate(
                    {},
                    [
                        traction["bottom_dual"].get("relative_dual"),
                        traction["top_dual"].get("relative_dual"),
                    ],
                    1.0e-8,
                )
                interface_e_pass = bool(
                    all(
                        np.isfinite(
                            float(
                                interface_continuity[side]["electric_tangential"][
                                    "relative_l2"
                                ]
                            )
                        )
                        and float(
                            interface_continuity[side]["electric_tangential"][
                                "relative_l2"
                            ]
                        )
                        <= 5.0e-3
                        for side in ("bottom", "top")
                    )
                )
                sample_finite = bool(
                    np.all(np.isfinite(selected_planes.electric_V_per_m))
                    and np.all(np.isfinite(selected_planes.magnetic_A_per_m))
                )
                orders = validation_raw["external_diffraction_orders"]
                order_keys: list[tuple[Any, ...]] = []
                order_rows_finite = True
                for row in orders:
                    row_ok = bool(
                        isinstance(row, dict)
                        and row.get("side") in {"bottom", "top"}
                        and isinstance(row.get("m"), int)
                        and not isinstance(row.get("m"), bool)
                        and isinstance(row.get("n"), int)
                        and not isinstance(row.get("n"), bool)
                        and row.get("polarization") in {"s", "p"}
                        and all(
                            np.isfinite(complex(row[key]).real)
                            and np.isfinite(complex(row[key]).imag)
                            for key in (
                                "total_projection",
                                "incident_projection",
                                "outgoing_amplitude",
                                "outgoing_amplitude_at_boundary",
                                "power_ratio",
                                "R",
                                "T",
                            )
                        )
                    )
                    order_rows_finite = bool(order_rows_finite and row_ok)
                    if row_ok:
                        order_keys.append(
                            (
                                row["side"],
                                row["m"],
                                row["n"],
                                row["polarization"],
                            )
                        )
                orders_finite = bool(
                    len(orders) == 80
                    and order_rows_finite
                    and len(order_keys) == len(set(order_keys))
                )
                energy_pass = bool(
                    np.isfinite(r_value)
                    and np.isfinite(t_value)
                    and np.isfinite(a_value)
                    and np.isfinite(a_volume)
                    and np.isfinite(closure_error)
                    and np.isfinite(balance_error)
                    and abs(closure_error) <= 1.0e-5
                )
                own_physics_pass = bool(
                    interface_e_pass
                    and traction_pass
                    and sample_finite
                    and orders_finite
                    and energy_pass
                )
                record["v4_telemetry"]["recovery_phase"] = "canonical"
                run_dir = Path(args.output).parent
                own_grid_path = run_dir / "v4_own_grid_EH_modal_q.npz"
                own_grid_meta = None
                if comm.rank == 0 and (not is_v6 or own_physics_pass):
                    own_grid_meta = _write_authority_grid_payload(
                        own_grid_path,
                        sample_x=sample_x,
                        sample_y=sample_y,
                        sample_z=sample_z,
                        electric=selected_planes.electric_V_per_m,
                        magnetic=selected_planes.magnetic_A_per_m,
                        modal=physical_solution.modal_amplitudes,
                        bottom_q=bottom_auxiliary,
                        top_q=top_auxiliary,
                        schema="task037b.v4-own-grid-EH-modal-q.v1",
                    )
                own_grid_meta = comm.bcast(own_grid_meta, root=0)
                canonical_exports = (
                    _write_canonical_manifest_exports(
                        systems=systems,
                        physical_solution=physical_solution,
                        run_dir=run_dir,
                        comm=comm,
                        prefix="task037b_v4",
                    )
                    if own_physics_pass
                    else {}
                )
                canonical_pass = bool(
                    own_physics_pass
                    and all(
                        canonical_exports.get(side, {})
                        .get("roles", {})
                        .get(role, {})
                        .get("pass")
                        is True
                        for side in ("bottom", "top")
                        for role in ("active_trace", "full_fe")
                    )
                )
                direct_comparator = {
                    "status": "not_run_authority_payload_gap",
                    "pass": False,
                    "modal_relative_l2": "not_run",
                    "bottom_canonical_relative_l2": "not_run",
                    "top_canonical_relative_l2": "not_run",
                }
                physics_pass = bool(own_physics_pass and canonical_pass)
                record["v4_telemetry"]["own_grid"] = own_grid_meta
                record["v4_telemetry"]["recovery_phase"] = "own_physics_and_canonical"
                record["v4_telemetry"]["physics_gates"] = {
                    "interface_e": {
                        "pass": interface_e_pass,
                        "reports": interface_continuity,
                    },
                    "exact_traction_dual": {
                        "pass": traction_pass,
                        "gate_role": traction_gate_role,
                        "reports": traction,
                    },
                    "middle_interface_samples_finite": sample_finite,
                    "external_orders_finite": orders_finite,
                    "external_order_reports": orders,
                    "energy": {
                        "closure_error": closure_error,
                        "A_balance_minus_A_volume": balance_error,
                        "pass": energy_pass,
                    },
                    "own_physics_pass": own_physics_pass,
                    "direct_hybrid_comparison": direct_comparator,
                    "pass": physics_pass,
                }
                if own_physics_pass and canonical_pass:
                    validation = {
                        "official_record": "candidate_measured_not_official",
                        "status": "measured_candidate_only",
                        "port_power": port_power,
                        "fe_modal_traction_equilibrium": traction,
                        "field_recovery": "measured_candidate_own_grid",
                        "field": {
                            "status": "measured_candidate_own_grid",
                            "own_grid": own_grid_meta,
                        },
                        "candidate_sample_grid": {
                            "shape": [5, 20, 40, 3],
                            "x_count": 40,
                            "y_count": 20,
                            "z_nm": sample_z.tolist(),
                            "own_grid": own_grid_meta,
                        },
                        "A_volume": absorption,
                        "canonical_export": {
                            "status": "measured_manifest_backed",
                            "grid_shape": [5, 20, 40, 3],
                            "sample_x_nm": sample_x.tolist(),
                            "sample_y_nm": sample_y.tolist(),
                            "sample_z_nm": sample_z.tolist(),
                            "electric": _array_descriptor(
                                selected_planes.electric_V_per_m
                            ),
                            "magnetic": _array_descriptor(
                                selected_planes.magnetic_A_per_m
                            ),
                            "own_grid": own_grid_meta,
                            "manifests": canonical_exports,
                            "pass": canonical_pass,
                        },
                        "R": r_value,
                        "T": t_value,
                        "A": a_value,
                        "orders": orders,
                        "external_diffraction_orders": orders,
                        "energy_closure": {
                            "R_plus_T_plus_A_volume": float(
                                r_value + t_value + a_volume
                            ),
                            "closure_error": closure_error,
                            "A_balance_minus_A_volume": balance_error,
                            "pass": energy_pass,
                        },
                        "external_auxiliary_recovery": recovery_gates,
                        "direct_hybrid_comparison": direct_comparator,
                        "12_plus_12": "not_run",
                        "Full3D": "not_run",
                        "full3d_comparison": "not_run",
                    }
                else:
                    validation = _v4_not_run_validation_boundary()
            else:
                recovery_phase = (
                    "external_auxiliary" if not external_recovery_pass else "full_fe"
                )
                record["v4_telemetry"]["recovery_phase"] = recovery_phase
                record["v4_telemetry"]["physics_gates"] = {
                    "external_recovery_pass": external_recovery_pass,
                    "full_fe_recovery_pass": full_fe_recovery_pass,
                    "pass": False,
                }
                validation = _v4_not_run_validation_boundary()
                recovery_pass = False
                own_physics_pass = False
                physics_pass = False
        else:
            validation = _v4_not_run_validation_boundary()
            recovery_pass = False
            own_physics_pass = False
            physics_pass = False
            record["v4_telemetry"]["recovery_phase"] = "numerical"
            record["v4_telemetry"]["physics_gates"] = {"pass": False}
        record["v4_telemetry"]["recovery_gates"] = recovery_gates
        record["v4_telemetry"]["canonical_export"] = (
            canonical_exports if numerical_pass else {}
        )
        complete_qualification_pass = bool(
            numerical_pass
            and recovery_pass
            and physics_pass
            and direct_comparator.get("pass", False)
        )
        record["validation"] = validation
        record["v4_telemetry"]["official_outputs"] = dict(validation)
        if numerical_pass and not external_recovery_pass:
            disposition = "FULL_LINEAR_SOLVE_PASS_EXTERNAL_RECOVERY_FAIL"
        elif numerical_pass and not full_fe_recovery_pass:
            disposition = "FULL_LINEAR_SOLVE_PASS_FULL_FE_RECOVERY_FAIL"
        elif numerical_pass and not own_physics_pass:
            disposition = "FULL_LINEAR_SOLVE_PASS_OWN_PHYSICS_GATE_FAIL"
        elif numerical_pass and not canonical_pass:
            disposition = "FULL_LINEAR_SOLVE_PASS_CANONICAL_GATE_FAIL"
        elif numerical_pass and not direct_comparator.get("pass", False):
            disposition = (
                "FULL_LINEAR_SOLVE_PASS_AWAITING_REVIEW_NOT_RUN_AUTHORITY_PAYLOAD_GAP"
            )
        elif numerical_pass and physics_pass:
            disposition = "DOUBLE_APPROXIMATE_MPI8_FULL_NUMERICAL_AND_PHYSICS_PASS"
        elif numerical_pass:
            disposition = "FULL_LINEAR_SOLVE_PASS_PHYSICS_GATE_FAIL"
        elif slow_contraction:
            disposition = "DOUBLE_APPROXIMATE_FULL_SLOW_CONTRACTION_AWAITING_REVIEW"
        else:
            disposition = "FIXED_ILU0_WOODBURY_BLOCK_PC_FULL_NEGATIVE"
        if v5_multimetric:
            if numerical_pass and (
                not recovery_pass or not own_physics_pass or not canonical_pass
            ):
                disposition = "MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL"
            elif (
                numerical_pass
                and own_physics_pass
                and canonical_pass
                and not direct_comparator.get("pass", False)
            ):
                disposition = (
                    "NUMERICAL_AND_OWN_PHYSICS_PASS_AUTHORITY_PAYLOAD_INCOMPLETE"
                )
            elif (
                not numerical_pass
                and v5_postsolve_audit.get("custom_convergence_false_positive") is True
            ):
                disposition = "CUSTOM_CONVERGENCE_FALSE_POSITIVE"
            elif not numerical_pass and solve_reason == -3 and solve_iterations == 700:
                disposition = "MULTIMETRIC_LINEAR_GATE_NOT_REACHED_BY_700"
            else:
                disposition = "V5_MULTIMETRIC_NUMERICAL_NEGATIVE"
            if v5_multimetric_telemetry is not None:
                v5_multimetric_telemetry[
                    "v6_disposition" if is_v6 else "v5_disposition"
                ] = disposition
        if is_v6:
            traction_gate = (
                record["v4_telemetry"]
                .get("physics_gates", {})
                .get("exact_traction_dual", {})
                .get("pass")
            )
            if not numerical_pass:
                if solve_reason > 0 and not v5_postsolve_audit.get("pass", False):
                    disposition = "TIGHT_CUSTOM_CONVERGENCE_FALSE_POSITIVE"
                elif solve_reason == -3 and solve_iterations == profile_max_it:
                    disposition = "TIGHT_LINEAR_GATE_NOT_REACHED_BY_1000"
                else:
                    disposition = "TIGHT_LINEAR_GATE_NOT_REACHED_BY_1000"
            elif not recovery_pass:
                disposition = "TIGHT_LINEAR_PASS_RECOVERY_FAIL"
            elif traction_gate is False:
                disposition = "TIGHT_LINEAR_PASS_EXACT_TRACTION_FAIL"
            elif not own_physics_pass or not canonical_pass:
                disposition = "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
            elif not direct_comparator.get("pass", False):
                disposition = (
                    "TIGHT_LINEAR_AND_OWN_PHYSICS_PASS_AUTHORITY_PAYLOAD_INCOMPLETE"
                )
            else:
                disposition = "DOUBLE_APPROXIMATE_MPI8_TIGHT_LINEAR_AND_PHYSICS_PASS"
            if v5_multimetric_telemetry is not None:
                v5_multimetric_telemetry["v6_disposition"] = disposition
        record["qualification"].update(
            {
                "numerical_pass": numerical_pass,
                "recovery_pass": recovery_pass,
                "own_physics_pass": own_physics_pass,
                "canonical_pass": canonical_pass,
                "complete_qualification_pass": complete_qualification_pass,
                "physics_pass": physics_pass,
                "recovery_phase": record["v4_telemetry"].get(
                    "recovery_phase", "not_run"
                ),
                "disposition": disposition,
            }
        )
        if is_v6:
            record["status"] = {
                "TIGHT_LINEAR_GATE_NOT_REACHED_BY_1000": "task037b_v6_tight_linear_gate_not_reached",
                "TIGHT_CUSTOM_CONVERGENCE_FALSE_POSITIVE": "task037b_v6_custom_convergence_false_positive",
                "TIGHT_LINEAR_PASS_RECOVERY_FAIL": "task037b_v6_linear_pass_recovery_failed",
                "TIGHT_LINEAR_PASS_EXACT_TRACTION_FAIL": "task037b_v6_linear_pass_exact_traction_failed",
                "TIGHT_LINEAR_AND_OWN_PHYSICS_PASS_AUTHORITY_PAYLOAD_INCOMPLETE": "task037b_v6_full_solve_awaiting_authority_payload",
                "DOUBLE_APPROXIMATE_MPI8_TIGHT_LINEAR_AND_PHYSICS_PASS": "task037b_v6_full_solve_pass",
            }.get(disposition, "task037b_v6_implementation_gate_failed")
        elif v5_multimetric and disposition == (
            "NUMERICAL_AND_OWN_PHYSICS_PASS_AUTHORITY_PAYLOAD_INCOMPLETE"
        ):
            record["status"] = "task037b_v5_full_solve_awaiting_authority_payload"
        elif v5_multimetric and disposition == (
            "MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL"
        ):
            record["status"] = "task037b_v5_linear_pass_recovery_or_physics_failed"
        elif v5_multimetric and disposition in {
            "MULTIMETRIC_LINEAR_GATE_NOT_REACHED_BY_700",
            "CUSTOM_CONVERGENCE_FALSE_POSITIVE",
            "V5_MULTIMETRIC_NUMERICAL_NEGATIVE",
        }:
            record["status"] = "task037b_v5_multimetric_numerical_negative"
        elif numerical_pass and complete_qualification_pass:
            record["status"] = "task037b_v4_full_solve_pass"
        elif numerical_pass and not external_recovery_pass:
            record["status"] = "task037b_v4_external_recovery_failed"
        elif numerical_pass and not full_fe_recovery_pass:
            record["status"] = "task037b_v4_full_fe_recovery_failed"
        elif numerical_pass and not own_physics_pass:
            record["status"] = "task037b_v4_own_physics_failed"
        elif numerical_pass and not canonical_pass:
            record["status"] = "task037b_v4_canonical_failed"
        elif numerical_pass and physics_pass:
            record["status"] = "task037b_v4_full_solve_awaiting_authority_payload"
        elif numerical_pass and recovery_pass:
            record["status"] = "task037b_v4_full_solve_physics_gate_failed"
        elif numerical_pass:
            record["status"] = "task037b_v4_full_solve_recovery_failed"
        else:
            record["status"] = "task037b_v4_full_solve_numerical_negative"
    except Exception as exc:
        implementation_error = f"{type(exc).__name__}: {exc}"
        if record is None:
            record = base_record()
        recovery_exception = bool(
            released
            and numerical_pass
            and record["qualification"].get("integration_pass") is True
        )
        if recovery_exception:
            recovery_error = implementation_error
            recovery_phase = str(
                record.get("v4_telemetry", {}).get(
                    "recovery_phase", "external_auxiliary"
                )
            )
            phase_status = {
                "external_auxiliary": "task037b_v4_external_recovery_failed",
                "full_fe": "task037b_v4_full_fe_recovery_failed",
                "own_physics": "task037b_v4_own_physics_failed",
                "canonical": "task037b_v4_canonical_failed",
            }
            phase_disposition = {
                "external_auxiliary": "FULL_LINEAR_SOLVE_PASS_EXTERNAL_RECOVERY_FAIL",
                "full_fe": "FULL_LINEAR_SOLVE_PASS_FULL_FE_RECOVERY_FAIL",
                "own_physics": "FULL_LINEAR_SOLVE_PASS_OWN_PHYSICS_GATE_FAIL",
                "canonical": "FULL_LINEAR_SOLVE_PASS_CANONICAL_GATE_FAIL",
            }
            if v5_multimetric:
                if is_v6:
                    traction_gate = (
                        record.get("v4_telemetry", {})
                        .get("physics_gates", {})
                        .get("exact_traction_dual", {})
                        .get("pass")
                    )
                    if recovery_phase in {"external_auxiliary", "full_fe"}:
                        record["status"] = "task037b_v6_linear_pass_recovery_failed"
                        v6_exception_disposition = "TIGHT_LINEAR_PASS_RECOVERY_FAIL"
                    elif traction_gate is False:
                        record["status"] = (
                            "task037b_v6_linear_pass_exact_traction_failed"
                        )
                        v6_exception_disposition = (
                            "TIGHT_LINEAR_PASS_EXACT_TRACTION_FAIL"
                        )
                    else:
                        record["status"] = "task037b_v6_implementation_gate_failed"
                        v6_exception_disposition = (
                            "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
                        )
                else:
                    record["status"] = (
                        "task037b_v5_linear_pass_recovery_or_physics_failed"
                    )
                if v5_multimetric_telemetry is not None:
                    v5_multimetric_telemetry[
                        "v6_disposition" if is_v6 else "v5_disposition"
                    ] = (
                        v6_exception_disposition
                        if is_v6
                        else "MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL"
                    )
            else:
                record["status"] = phase_status.get(
                    recovery_phase, "task037b_v4_recovery_gate_failed"
                )
            record["qualification"].update(
                {
                    "numerical_pass": True,
                    "recovery_pass": bool(recovery_pass),
                    "own_physics_pass": bool(own_physics_pass),
                    "canonical_pass": bool(canonical_pass),
                    "complete_qualification_pass": False,
                    "physics_pass": bool(physics_pass),
                    "disposition": (
                        v6_exception_disposition
                        if is_v6
                        else "MULTIMETRIC_LINEAR_PASS_RECOVERY_OR_PHYSICS_FAIL"
                        if v5_multimetric
                        else phase_disposition.get(
                            recovery_phase, "FULL_LINEAR_SOLVE_PASS_PHYSICS_GATE_FAIL"
                        )
                    ),
                    "recovery_phase": recovery_phase,
                    "recovery_error": recovery_error,
                }
            )
            record["v4_telemetry"]["recovery_error"] = recovery_error
            record["v4_telemetry"]["recovery_phase"] = recovery_phase
        else:
            if v5_multimetric:
                record["status"] = (
                    "task037b_v6_implementation_gate_failed"
                    if is_v6
                    else "task037b_v5_implementation_gate_failed"
                )
                if v5_multimetric_telemetry is not None:
                    v5_multimetric_telemetry[
                        "v6_disposition" if is_v6 else "v5_disposition"
                    ] = "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
            else:
                record["status"] = "task037b_v4_implementation_gate_failed"
            record["qualification"].update(
                {
                    "integration_pass": False,
                    "numerical_pass": bool(numerical_pass),
                    "recovery_pass": False,
                    "physics_pass": False,
                    "disposition": "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED",
                    "implementation_error": implementation_error,
                }
            )
        record["validation"] = _v4_not_run_validation_boundary()
        record["v4_telemetry"]["official_outputs"] = dict(record["validation"])
    finally:
        if not released:
            release_action_stack()
        if full_result is not None:
            full_result.destroy()
            if v5_multimetric:
                v5_snapshot_destroyed = bool(getattr(full_result, "_destroyed", False))
            full_result = None
        if physical_solution is not None:
            physical_solution.destroy()
            if v5_multimetric:
                v5_bottom_snapshot_destroyed = bool(
                    getattr(physical_solution, "_destroyed", False)
                )
                v5_top_snapshot_destroyed = v5_bottom_snapshot_destroyed
                physical_solution.modal_amplitudes = None
                v5_modal_snapshot_released = True
        else:
            if candidate_bottom is not None:
                candidate_bottom.destroy()
                v5_bottom_snapshot_destroyed = bool(v5_multimetric)
            if candidate_top is not None:
                candidate_top.destroy()
                v5_top_snapshot_destroyed = bool(v5_multimetric)
            if candidate_modal is not None:
                candidate_modal = None
                v5_modal_snapshot_released = bool(v5_multimetric)
        if bottom_auxiliary_vec is not None:
            bottom_auxiliary_vec.destroy()
        if top_auxiliary_vec is not None:
            top_auxiliary_vec.destroy()
        if record is not None:
            telemetry = record.setdefault("v4_telemetry", {})
            telemetry["stage_markers"] = list(stage_markers)
            if v5_multimetric:
                if v5_snapshot_metadata.get("status") == "measured":
                    v5_snapshot_release.update(
                        {
                            "status": "measured",
                            "snapshot_destroyed": v5_snapshot_destroyed,
                            "bottom_snapshot_destroyed": v5_bottom_snapshot_destroyed,
                            "top_snapshot_destroyed": v5_top_snapshot_destroyed,
                            "modal_snapshot_released": v5_modal_snapshot_released,
                        }
                    )
                else:
                    v5_snapshot_release.update(
                        {
                            "status": "not_run_dependency_gate",
                            "snapshot_destroyed": None,
                            "bottom_snapshot_destroyed": None,
                            "top_snapshot_destroyed": None,
                            "modal_snapshot_released": None,
                        }
                    )
                if v5_multimetric_telemetry is not None:
                    v5_multimetric_telemetry["snapshot_release"] = v5_snapshot_release
            release_telemetry = dict(telemetry.get("release", {}))
            release_pass = bool(
                all(
                    release_ledger.get(side, {}).get("release_pass") is True
                    for side in ("bottom", "top")
                )
                and outer_release.get("destroy_calls_complete") is True
            )
            if v5_multimetric and numerical_pass:
                release_pass = bool(
                    release_pass
                    and v5_snapshot_metadata.get("pass") is True
                    and v5_release_repeat.get("pass") is True
                    and v5_snapshot_release.get("snapshot_destroyed") is True
                    and v5_snapshot_release.get("bottom_snapshot_destroyed") is True
                    and v5_snapshot_release.get("top_snapshot_destroyed") is True
                    and v5_snapshot_release.get("modal_snapshot_released") is True
                )
            release_telemetry.update(
                {
                    "sides": dict(release_ledger),
                    "outer": dict(outer_release),
                    "release_pass": release_pass,
                }
            )
            telemetry["release"] = release_telemetry
            if v5_multimetric and v5_multimetric_telemetry is not None:
                v5_multimetric_telemetry["release_pass"] = release_pass
                if not release_pass:
                    record["qualification"]["integration_pass"] = False
                    record["qualification"]["disposition"] = (
                        "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
                    )
                    record["qualification"]["implementation_error"] = (
                        "V5 snapshot/release lifecycle contract failed."
                    )
                    record["status"] = (
                        "task037b_v6_implementation_gate_failed"
                        if is_v6
                        else "task037b_v5_implementation_gate_failed"
                    )
                    v5_multimetric_telemetry[
                        "v6_disposition" if is_v6 else "v5_disposition"
                    ] = "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
            record["timing_seconds_max_rank"] = {
                **timings,
                "v4_total": _max_elapsed(comm, total_started),
            }
            if v5_multimetric:
                telemetry_key = "v6_telemetry" if is_v6 else "v5_telemetry"
                record[telemetry_key] = dict(telemetry.get("multimetric", {}))
                record[telemetry_key]["stage_markers"] = list(stage_markers)
                if is_v6:
                    record["qualification"]["v6_traction_aligned"] = True
                else:
                    record["qualification"]["v5_multimetric"] = True
    raise _V4QualificationStop(record)


def _run_v2_block_screen(
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
    timings: dict[str, float],
    total_started: float,
    mark_stage,
    progress,
) -> None:
    """Run one explicit-opt-in bounded V2 or V3 action block screen and stop."""

    is_v3 = bool(args.task037b_v3_gate)
    screen_profile = "double" if is_v3 else args.task037b_v2_profile
    screen_max_it = 200 if is_v3 else int(args.task037b_v2_max_it)
    record_schema = (
        "task037b.v3-progressive-block-pc-screen.v1"
        if is_v3
        else "task037b.v2-block-pc-screen.v1"
    )
    telemetry_key = "v3_telemetry" if is_v3 else "v2_telemetry"
    gate_prefix = "v3" if is_v3 else "v2"
    selections = _h5_frozen_mode_selection(positive, negative)
    layout = None
    action_matrix = None
    action_context = None
    outer_rhs = None
    preconditioner = None
    rhs_sets: dict[str, list[tuple[str, PETSc.Vec, dict[str, Any]]]] = {}
    side_actions: dict[str, Any] = {}
    side_components: dict[str, Any] = {}
    side_fixed: dict[str, Any] = {}
    side_woodbury: dict[str, Any] = {}
    side_oracles: dict[str, Any] = {}
    screen_result = None
    screen_gate = None
    side_records: dict[str, dict[str, Any]] = {"bottom": {}, "top": {}}
    release_records: dict[str, dict[str, Any]] = {"bottom": {}, "top": {}}
    record: dict[str, Any] | None = None
    started = time.perf_counter()
    v3_stage_markers: list[str] = (
        ["action_coupling_build_started", "action_coupling_build_ready"]
        if is_v3
        else []
    )

    def record_stage(stage: str) -> None:
        mark_stage(stage)
        if is_v3:
            v3_stage_markers.append(stage)

    approximate_side = {
        "bottom-approx": "bottom",
        "top-approx": "top",
        "double": None,
    }[screen_profile]
    exact_side = (
        None
        if approximate_side is None
        else "top"
        if approximate_side == "bottom"
        else "bottom"
    )
    systems = {"bottom": bottom, "top": top}
    blocks = {"bottom": coupling.bottom, "top": coupling.top}

    try:
        record_stage("v3_action_block_setup" if is_v3 else "v2_action_block_setup")
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
        outer_rhs = layout.pack(
            bottom.b,
            top.b,
            internal_modal_rhs_correction(coupling),
        )
        global_operator_inventory = dict(action_context.inventory)
        if "p6_direct_factor_count" not in global_operator_inventory:
            raise RuntimeError("V2 global operator inventory lacks p6 factor count.")
        global_direct_factor_count = global_operator_inventory["p6_direct_factor_count"]
        if global_direct_factor_count is None:
            raise RuntimeError("V2 global operator factor count is unavailable.")
        global_direct_factor_count = int(global_direct_factor_count)
        global_operator_contract = bool(
            global_operator_inventory.get("global_A_materialized") is False
            and global_operator_inventory.get("matrix_free") is True
            and global_direct_factor_count == 0
        )
        if not global_operator_contract:
            raise RuntimeError("V2 global operator contract failed.")

        for side in ("bottom", "top"):
            if approximate_side is None or side == approximate_side:
                if is_v3:
                    record_stage(f"{side}_approx_setup_started")
                components = create_hybrid_local_dtn_action_components(systems[side])
                side_components[side] = components
                fixed = build_hybrid_whole_endcap_fixed_smoother_action(systems[side])
                side_fixed[side] = fixed
                woodbury = HybridLocalDtnWoodburyFixedAction(fixed, components)
                side_woodbury[side] = woodbury
                side_actions[side] = woodbury
                if is_v3:
                    record_stage(f"{side}_approx_setup_ready")
            elif side == exact_side:
                direct_system = None
                try:
                    direct_system = assemble_hybrid_local_dtn_system(
                        cfg,
                        side,
                        bottom_interface_z_nm=args.bottom_interface_nm,
                        top_interface_z_nm=args.top_interface_nm,
                        local_mesh_override=systems[side].local_mesh,
                    )
                    oracle = _h3_oracle_local_system(direct_system)
                    side_oracles[side] = oracle
                finally:
                    if direct_system is not None:
                        direct_system.destroy()
                factor, factor_setup = _factor_local(oracle.A)
                direct_action = HybridBlockLduDirectAction(
                    oracle.A,
                    factor,
                    _local_factor_inventory(factor),
                )
                side_actions[side] = direct_action
                side_records[side].update(
                    {
                        "factor_setup_seconds": float(factor_setup),
                    }
                )

        def v3_callback_certificate_pass(cert: dict[str, Any] | None) -> bool:
            return bool(
                cert is not None
                and cert["wrapper_vs_internal_woodbury_error"] <= 1.0e-12
                and cert["linearity_error"] <= 1.0e-12
                and cert["determinism_error"] <= 1.0e-14
                and cert["repeat_hash_equal"]
                and cert["woodbury"].get("K_rank") == R4_MODAL_COUNT
                and np.isfinite(float(cert["woodbury"].get("K_condition_number")))
                and float(cert["woodbury"]["K_condition_number"]) <= 1.0e6
                and cert["woodbury"].get("arrays_finite") is True
                and cert["base_factor_count"] == 1
                and cert["local_direct_factor_count"] == 0
                and cert["nested_ksp_created"] is False
                and cert["apply_count_increment"] == 7
            )

        certificates = {}
        for side in ("bottom", "top"):
            if side in side_woodbury:
                certificates[side] = _v2_fixed_callback_certificate(side_woodbury[side])
                certificate_pass = (
                    v3_callback_certificate_pass(certificates[side])
                    if is_v3
                    else bool(certificates[side]["pass"])
                )
                if not certificate_pass:
                    raise RuntimeError(
                        f"{('V3' if is_v3 else 'V2')} fixed callback certificate failed for {side}."
                    )
            else:
                certificates[side] = None

        if approximate_side is not None:
            rhs_sets[approximate_side] = _h5_rhs_set(
                systems[approximate_side],
                blocks[approximate_side],
                selections,
                side=approximate_side,
                propagation=coupling.propagation,
            )
            rho_records = []
            rhs_list = rhs_sets[approximate_side]
            while rhs_list:
                name, vector, metadata = rhs_list.pop(0)
                if float(vector.norm()) <= 1.0e-30:
                    vector.destroy()
                    continue
                target = systems[approximate_side].A.createVecLeft()
                before = int(side_actions[approximate_side].diagnostics["apply_count"])
                try:
                    side_actions[approximate_side].apply(vector, target)
                    rho = _h5_true_relative_residual(
                        systems[approximate_side].A,
                        vector,
                        target,
                    )
                    after = int(
                        side_actions[approximate_side].diagnostics["apply_count"]
                    )
                    rho_records.append(
                        {
                            "name": name,
                            "metadata": dict(metadata),
                            "source_digest": _h1_owned_vec_digest(vector),
                            "rho": float(rho),
                            "apply_count_before": before,
                            "apply_count_after": after,
                            "finite": bool(np.isfinite(rho)),
                            "apply_count_increment": after - before,
                            "pass": bool(after - before == 1 and np.isfinite(rho)),
                        }
                    )
                finally:
                    target.destroy()
                    vector.destroy()
            rhs_sets[approximate_side] = []
            expected_nonzero = 10 if approximate_side == "bottom" else 11
            if len(rho_records) != expected_nonzero or not all(
                item["pass"] for item in rho_records
            ):
                raise RuntimeError(
                    f"V2 one-apply diagnostic failed for {approximate_side}."
                )
            side_records[approximate_side].update(
                {
                    "rho_records": rho_records,
                    "nonzero_rhs_count": len(rho_records),
                    "one_apply_diagnostic": {
                        "status": "pass",
                        "expected_nonzero_rhs_count": expected_nonzero,
                    },
                }
            )
        else:
            for side in ("bottom", "top"):
                side_records[side]["one_apply_diagnostic"] = {
                    "status": "not_run_here",
                    "authority": "one-sided B/T required",
                }

        expected_factors = {
            "bottom-approx": {"bottom": (0, 1), "top": (1, 0)},
            "top-approx": {"bottom": (1, 0), "top": (0, 1)},
            "double": {"bottom": (0, 1), "top": (0, 1)},
        }[screen_profile]
        factor_identity = {}
        for side in ("bottom", "top"):
            diagnostics = dict(side_actions[side].diagnostics)
            direct_count = int(
                diagnostics.get(
                    "direct_factor_count",
                    diagnostics.get("local_direct_factor_count", 0),
                )
            )
            ilu_count = int(
                diagnostics.get(
                    "ilu_factor_count", diagnostics.get("base_factor_count", 0)
                )
            )
            expected_direct, expected_ilu = expected_factors[side]
            factor_identity[side] = {
                "direct_factor_count": direct_count,
                "ilu_factor_count": ilu_count,
                "borrowed_local_factor_count": direct_count + ilu_count,
                "expected_direct_factor_count": expected_direct,
                "expected_ilu_factor_count": expected_ilu,
                "pass": bool(
                    direct_count == expected_direct and ilu_count == expected_ilu
                ),
            }
            side_records[side]["factor_identity"] = factor_identity[side]
        factor_identity_pass = bool(
            all(item["pass"] for item in factor_identity.values())
            and sum(
                item["borrowed_local_factor_count"] for item in factor_identity.values()
            )
            == 2
        )
        if not factor_identity_pass:
            raise RuntimeError("V2 fixed-side factor identity failed.")

        if is_v3:
            record_stage("modal_schur_build_started")
        preconditioner = create_action_block_ldu_preconditioner(
            layout,
            bottom,
            top,
            coupling,
            side_actions["bottom"],
            side_actions["top"],
        )
        pc_setup_inventory = dict(preconditioner.inventory)
        pc_inventory_pass = bool(
            pc_setup_inventory.get("global_A_materialized") is False
            and pc_setup_inventory.get("borrowed_local_factor_count") == 2
            and pc_setup_inventory.get("pc_owned_local_factor_count") == 0
            and all(
                pc_setup_inventory.get(f"{side}_direct_factor_count")
                == expected_factors[side][0]
                and pc_setup_inventory.get(f"{side}_ilu_factor_count")
                == expected_factors[side][1]
                for side in ("bottom", "top")
            )
        )
        if not pc_inventory_pass:
            raise RuntimeError("V2 PC factor inventory contract failed.")
        if is_v3:
            record_stage("modal_schur_build_ready")
        online_before = {
            side: int(side_actions[side].diagnostics["apply_count"])
            for side in ("bottom", "top")
        }
        setup_seconds = _max_elapsed(comm, started)
        setup_key = "v3_action_block_setup" if is_v3 else "v2_action_block_setup"
        timings[setup_key] = setup_seconds
        if not is_v3:
            record_stage("v2_outer_screen")
        started = time.perf_counter()
        v3_checkpoint_events = {
            20: "outer_iter_20",
            60: "outer_iter_60",
            100: "outer_iter_100",
            200: "outer_iter_200",
        }

        def v3_checkpoint_callback(row: dict[str, Any]) -> None:
            event = v3_checkpoint_events.get(int(row["iteration"]))
            if event is not None:
                record_stage(event)

        screen_result = screen_action_block_ldu(
            action_matrix,
            outer_rhs,
            preconditioner,
            max_it=screen_max_it,
            v3_progressive=is_v3,
            checkpoint_callback=v3_checkpoint_callback if is_v3 else None,
        )
        preconditioner_after = dict(preconditioner.inventory)
        preconditioner = None
        pc_apply_seconds_local = float(screen_result.pc_apply_seconds)
        pc_apply_seconds_max = float(comm.allreduce(pc_apply_seconds_local, op=MPI.MAX))
        screen_key = "v3_outer_screen" if is_v3 else "v2_outer_screen"
        timings[screen_key] = _max_elapsed(comm, started)
        screen_gate = (
            action_block_v3_progressive_gate(
                screen_result.history,
                converged_reason=int(screen_result.converged_reason),
                final=True,
            )
            if is_v3
            else action_block_screen_gate(
                screen_result.history,
                profile=screen_profile,
                max_it=screen_max_it,
                converged_reason=int(screen_result.converged_reason),
            )
        )
        online_after = {
            side: int(side_actions[side].diagnostics["apply_count"])
            for side in ("bottom", "top")
        }
        online_counts = {
            side: {
                "before": online_before[side],
                "after": online_after[side],
                "increment": online_after[side] - online_before[side],
                "expected_increment": 2
                * int(screen_result.inventory["pc_apply_count"]),
                "pass": online_after[side] - online_before[side]
                == 2 * int(screen_result.inventory["pc_apply_count"]),
            }
            for side in ("bottom", "top")
        }
        for side in ("bottom", "top"):
            side_records[side].update(
                {
                    "action_diagnostics_before_release": dict(
                        side_actions[side].diagnostics
                    ),
                    "online_apply": online_counts[side],
                    "borrowed_action_survives_after_screen": bool(
                        not side_actions[side].diagnostics.get("destroyed", False)
                    ),
                }
            )

        modal_diagnostics = dict(screen_result.inventory["modal_schur"])
        modal_condition_limit = 1.0e6 if is_v3 else 1.0e12
        modal_repeat_limit = 1.0e-12 if is_v3 else 1.0e-13
        expected_modal_shape = (
            [240, 240] if is_v3 else [int(coupling.internal_unknown_count)] * 2
        )
        expected_modal_rank = 240 if is_v3 else coupling.internal_unknown_count
        modal_contract = bool(
            (not is_v3 or coupling.internal_unknown_count == 240)
            and modal_diagnostics.get("shape") == expected_modal_shape
            and modal_diagnostics.get("rank") == expected_modal_rank
            and np.isfinite(float(modal_diagnostics.get("condition")))
            and float(modal_diagnostics["condition"]) <= modal_condition_limit
            and modal_diagnostics.get("finite") is True
            and (
                not is_v3
                or (
                    modal_diagnostics.get("dtype") == "complex128"
                    and modal_diagnostics.get("normal_equations") is False
                )
            )
            and float(modal_diagnostics["matrix_repeat_error"]) <= modal_repeat_limit
            and float(modal_diagnostics["lu_repeat_solve_error"]) <= modal_repeat_limit
            and all(
                value == 2 * coupling.internal_unknown_count
                for value in modal_diagnostics["build_apply_count"].values()
            )
        )
        callback_contract = (
            bool(
                all(
                    v3_callback_certificate_pass(cert) for cert in certificates.values()
                )
            )
            if is_v3
            else bool(
                all(
                    certificates[side] is not None and certificates[side]["pass"]
                    for side in ("bottom", "top")
                    if side == approximate_side
                )
                and all(
                    item["pass"] for item in certificates.values() if item is not None
                )
            )
        )
        v3_inventory_pass = True
        if is_v3:
            v3_inventory_pass = bool(
                global_direct_factor_count == 0
                and global_operator_inventory.get("global_A_materialized") is False
                and all(
                    systems[side].inventory.get("fine_global_A_materialized") is False
                    and systems[side].inventory.get("explicit_external_c_matrix_count")
                    == 0
                    and systems[side].inventory.get("explicit_external_d_matrix_count")
                    == 0
                    for side in ("bottom", "top")
                )
            )
        side_contract = bool(
            all(item["online_apply"]["pass"] for item in side_records.values())
            and all(
                item["borrowed_action_survives_after_screen"]
                for item in side_records.values()
            )
        )
        prediction_iterations = [
            int(row["iteration"])
            for row in screen_result.history
            if 120 <= int(row["iteration"]) <= 200
        ]
        v3_prediction_contract = bool(
            not is_v3
            or screen_gate.get("stage") != 200
            or (
                screen_gate.get("prediction_interval") == [120, 200]
                and screen_gate.get("prediction_sample_count") == 81
                and prediction_iterations == list(range(120, 201))
                and all(
                    np.isfinite(float(row["global_true_relative_residual"]))
                    and float(row["global_true_relative_residual"]) >= 0.0
                    for row in screen_result.history
                    if 120 <= int(row["iteration"]) <= 200
                )
            )
        )
        integration_pass = bool(
            modal_contract
            and callback_contract
            and factor_identity_pass
            and pc_inventory_pass
            and global_operator_contract
            and side_contract
            and v3_inventory_pass
            and v3_prediction_contract
        )
        for side in ("bottom", "top"):
            system = systems[side]
            object_ledger = {
                "inventory": dict(system.inventory),
                "base_matrix_stats": dict(system.base_matrix_stats),
                "augmented_matrix_stats": dict(system.augmented_matrix_stats),
                "coupling_stats": dict(system.coupling_stats),
                "static_condensation": system.static_condensation.metadata.to_dict(),
            }
            if side in side_components:
                components = side_components[side]
                component_matrices = {
                    name: getattr(components, name) for name in ("F", "C", "D", "H")
                }
                object_ledger["components"] = {
                    "h_condition_number": float(components.h_condition_number),
                    "matrices": {
                        name: {
                            "type": str(matrix.getType()),
                            "global_size": list(matrix.getSize()),
                            "local_size": list(matrix.getLocalSize()),
                        }
                        for name, matrix in component_matrices.items()
                    },
                }
            side_records[side]["object_ledger"] = object_ledger
        record_started = time.perf_counter()
        restart_local_rows = int(action_matrix.getLocalSize()[0])
        restart_local_bytes = int(
            (2 * 90 + 1) * restart_local_rows * np.dtype(np.complex128).itemsize
        )
        restart_rows_by_rank = [
            int(value) for value in comm.allgather(restart_local_rows)
        ]
        restart_bytes_by_rank = [
            int(value) for value in comm.allgather(restart_local_bytes)
        ]
        record_stage("v3_record" if is_v3 else "v2_record")
        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        v3_bounded_pass = bool(is_v3 and screen_gate.get("bounded_convergence") is True)
        v3_numerical_pass = bool(
            screen_gate["pass"] if not is_v3 else screen_gate["pass"] or v3_bounded_pass
        )
        v3_slow = bool(
            is_v3
            and not v3_numerical_pass
            and screen_gate.get("finite") is True
            and screen_gate.get("r200") is not None
            and 0.05 < float(screen_gate["r200"]) <= 0.12
            and screen_gate.get("last40_net_decrease") is True
            and screen_gate.get("q160_200") is not None
            and float(screen_gate["q160_200"]) < 0.995
            and screen_gate.get("reported_true_agree") is True
            and screen_gate.get("hard_stop") is False
            and screen_result.progressive_stop_cause is None
            and all(
                screen_gate.get("gates", {}).get(checkpoint) is True
                for checkpoint in ("20", "60", "100")
            )
        )
        v3_classification_code = (
            "PASS"
            if v3_numerical_pass
            else "SLOW"
            if v3_slow
            else "FAMILY_NEGATIVE"
            if is_v3
            else None
        )
        v3_classification = {
            "PASS": "DOUBLE_APPROXIMATE_200_STEP_PASS_AWAITING_FULL_REVIEW",
            "SLOW": "DOUBLE_APPROXIMATE_SLOW_CONTRACTION_AWAITING_REVIEW",
            "FAMILY_NEGATIVE": "FIXED_ILU0_WOODBURY_BLOCK_PC_FAMILY_NEGATIVE",
        }.get(v3_classification_code)
        initial_status = (
            (
                "task037b_v3_pass"
                if v3_classification_code == "PASS"
                else "task037b_v3_slow"
                if v3_classification_code == "SLOW"
                else "task037b_v3_family_negative"
            )
            if is_v3 and integration_pass
            else "task037b_v3_implementation_gate_failed"
            if is_v3
            else "task037b_v2_screen_pass"
            if integration_pass and screen_gate["pass"]
            else "task037b_v2_screen_numerical_negative"
            if integration_pass
            else "task037b_v2_screen_contract_failed"
        )
        record = {
            "schema_version": 1,
            "record_schema": record_schema,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "benchmark_id": (
                "task037b_v3_progressive_block_pc_screen"
                if is_v3
                else "task037b_v2_bounded_block_pc_screen"
            ),
            "official_record": False,
            "status": initial_status,
            "metadata": {
                **provenance,
                "command": list(sys.argv),
                "verified_clean_sha": args.verified_clean_sha,
                "authority_gate": authority_gate,
            },
            "case": {
                "degree": args.degree,
                "h_nm": args.h_nm,
                "modal_degree": args.modal_degree,
                "modal_h_nm": args.modal_h_nm,
                "requested_modes": args.requested_modes,
                "candidate_modes": args.candidate_modes,
                "wavelength_nm": float(cfg.lambda0),
                "mpi_size": comm.size,
                "polarization_kind": args.polarization_kind,
                "incident_grazing_deg": args.incident_grazing_deg,
                "bottom_interface_nm": args.bottom_interface_nm,
                "top_interface_nm": args.top_interface_nm,
                "solver_path": args.solver_path,
                "internal_propagation_model": args.internal_propagation_model,
                "internal_traction_model": args.internal_traction_model,
                "stage4_full3d_assembly_backend": (args.stage4_full3d_assembly_backend),
                **(
                    {"v3_gate": True}
                    if is_v3
                    else {
                        "v2_profile": args.task037b_v2_profile,
                        "v2_max_it": args.task037b_v2_max_it,
                    }
                ),
            },
            "hybrid_system": {
                "operator_inventory": global_operator_inventory,
                "matrix_size": list(action_matrix.getSize()),
                "local_matrix_size": list(action_matrix.getLocalSize()),
                "matrix_type": str(action_matrix.getType()),
                "global_A_materialized": False,
                "global_direct_factor_count": global_direct_factor_count,
                "global_operator_contract": global_operator_contract,
                "side_factor_identity": factor_identity,
                "pc_owned_local_factor_count": int(
                    pc_setup_inventory["pc_owned_local_factor_count"]
                ),
            },
            "screen": {
                "profile": screen_profile,
                "max_it": screen_max_it,
                "restart": 90,
                "rtol": 1.0e-6,
                "atol": 0.0,
                "zero_initial": True,
                "outer_solver": "fgmres",
                "pc_side": "right",
                "converged_reason": int(screen_result.converged_reason),
                "iterations": int(screen_result.iterations),
                "reported_final": float(
                    screen_result.history[-1]["reported_relative_residual"]
                ),
                "final_true_relative_residual": float(
                    screen_result.final_true_relative_residual
                ),
                "minimum_true_relative_residual": float(
                    screen_result.minimum_true_relative_residual
                ),
                "history": screen_result.history,
                "last5": screen_result.last5,
                "last40": screen_result.last40,
                "gate": screen_gate,
                **(
                    {
                        "progressive_stop_cause": screen_result.progressive_stop_cause,
                        "effective_stop_cause": (
                            screen_result.progressive_stop_cause
                            or screen_gate.get("stop_cause")
                        ),
                    }
                    if is_v3
                    else {}
                ),
                "inventory_before_release": screen_result.inventory,
                "inventory_after_release": preconditioner_after,
                "pc_apply_seconds_max_rank": pc_apply_seconds_max,
                "pc_apply_seconds_local": pc_apply_seconds_local,
            },
            telemetry_key: {
                **({"task037b_v3_gate": True} if is_v3 else {"task037b_v2_gate": True}),
                "profile": screen_profile,
                "max_it": screen_max_it,
                "frozen_mode_selection": selections,
                "sides": side_records,
                "fixed_callback_certificates": certificates,
                "modal_schur": modal_diagnostics,
                "modal_schur_contract_pass": modal_contract,
                "factor_identity": factor_identity,
                "factor_identity_pass": factor_identity_pass,
                "global_operator_inventory": global_operator_inventory,
                "global_operator_contract": global_operator_contract,
                "pc_setup_inventory": pc_setup_inventory,
                "pc_inventory_pass": pc_inventory_pass,
                "online_apply_counts": online_counts,
                "pc_apply_seconds_max_rank": pc_apply_seconds_max,
                "pc_apply_seconds_local": pc_apply_seconds_local,
                "release_records": release_records,
                "release_pass": False,
                "restart_basis_bytes": {
                    "derived_estimate": True,
                    "formula": "(2*restart+1)*rows*complex128_bytes",
                    "local_rows": int(action_matrix.getLocalSize()[0]),
                    "global_rows": int(action_matrix.getSize()[0]),
                    "local_bytes": restart_local_bytes,
                    "global_bytes": int(
                        (2 * 90 + 1)
                        * action_matrix.getSize()[0]
                        * np.dtype(np.complex128).itemsize
                    ),
                    "rows_by_rank": restart_rows_by_rank,
                    "bytes_by_rank": restart_bytes_by_rank,
                    "sum_rows": int(sum(restart_rows_by_rank)),
                    "max_rows": int(max(restart_rows_by_rank)),
                    "sum_bytes": int(sum(restart_bytes_by_rank)),
                    "max_bytes": int(max(restart_bytes_by_rank)),
                },
                "ordinary_default_changed": False,
                **({"stage_markers": list(v3_stage_markers)} if is_v3 else {}),
                **(
                    {
                        "classification": v3_classification,
                        "classification_code": v3_classification_code,
                        "bounded_convergence": v3_bounded_pass,
                        "progressive_stop_cause": screen_result.progressive_stop_cause,
                        "prediction_contract": v3_prediction_contract,
                        "prediction_formula": (
                            "log(r_i)=slope*i+intercept; "
                            "i_target=(log(1e-6)-intercept)/slope"
                        ),
                        "official_outputs": {
                            "R": "not_run",
                            "T": "not_run",
                            "A": "not_run",
                            "A_volume": "not_run",
                            "orders": "not_run",
                            "field": "not_run",
                            "12_plus_12": "not_run",
                            "Full3D": "not_run",
                        },
                        "v3_release": False,
                    }
                    if is_v3
                    else {}
                ),
            },
            "validation": {
                **_v2_not_run_validation_boundary(),
                **(
                    {
                        "official_outputs": {
                            "R": "not_run",
                            "T": "not_run",
                            "A": "not_run",
                            "A_volume": "not_run",
                            "orders": "not_run",
                            "field": "not_run",
                            "12_plus_12": "not_run",
                            "Full3D": "not_run",
                        }
                    }
                    if is_v3
                    else {}
                ),
            },
            "physical_field_reconstruction": {"status": "not_run"},
            "gates": (
                {
                    "v3_fixed_callback_certificate": callback_contract,
                    "v3_modal_schur": modal_contract,
                    "v3_online_apply_counts": side_contract,
                    "v3_factor_identity": factor_identity_pass,
                    "v3_global_operator": global_operator_contract,
                    "v3_pc_inventory": pc_inventory_pass,
                    "v3_action_inventory": v3_inventory_pass,
                    "v3_prediction": v3_prediction_contract,
                    "v3_release": False,
                    "v3_screen": bool(screen_gate["pass"]),
                    "v3_integration_pass": integration_pass,
                    "v3_worker_numerical_pass": v3_numerical_pass,
                }
                if is_v3
                else {
                    "v2_fixed_callback_certificate": callback_contract,
                    "v2_modal_schur": modal_contract,
                    "v2_online_apply_counts": side_contract,
                    "v2_factor_identity": factor_identity_pass,
                    "v2_global_operator": global_operator_contract,
                    "v2_pc_inventory": pc_inventory_pass,
                    "v2_release": False,
                    "v2_screen": bool(screen_gate["pass"]),
                    "v2_integration_pass": integration_pass,
                    "v2_worker_numerical_pass": bool(screen_gate["pass"]),
                }
            ),
            "qualification": {
                **({"task037b_v3_gate": True} if is_v3 else {"task037b_v2_gate": True}),
                "profile": screen_profile,
                "max_it": screen_max_it,
                "integration_pass": integration_pass,
                "worker_numerical_pass": v3_numerical_pass
                if is_v3
                else bool(screen_gate["pass"]),
                "official_record": False,
                "disposition": (
                    v3_classification
                    if is_v3 and integration_pass
                    else "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
                    if is_v3
                    else "screen_pass"
                    if integration_pass and screen_gate["pass"]
                    else "screen_numerical_negative"
                    if integration_pass
                    else "implementation_contract_failed"
                ),
                "boundary": (
                    (
                        "V3 progressive double block-PC screen only; no field, R/T/A, "
                        if is_v3
                        else "V2 bounded block-PC screen only; no field, R/T/A, "
                    )
                    + "external diffraction, 12+12, or Full3D comparison."
                ),
            },
            "timing_seconds_max_rank": {
                **timings,
                ("v3_record" if is_v3 else "v2_record"): _max_elapsed(
                    comm, record_started
                ),
                "total": _max_elapsed(comm, total_started),
            },
            "historical_peak_rss_mb_by_rank": comm.gather(
                _historical_peak_rss_mb(), root=0
            ),
            "memory_semantics": (
                (
                    "V3 progressive screen worker historical per-rank RSS; external "
                    if is_v3
                    else "V2 bounded screen worker historical per-rank RSS; external "
                )
                + "watchdog owns simultaneous resource classification."
            ),
        }
    finally:
        v2_release_started = time.perf_counter()
        if is_v3:
            record_stage("release_started")
        if preconditioner is not None:
            preconditioner.destroy()
        for rhs_list in rhs_sets.values():
            for _name, vector, _metadata in rhs_list:
                vector.destroy()

        # Release in ownership phases: PC context, Woodbury data, fixed bases,
        # components, direct carriers, then oracle matrices.
        for side, woodbury in side_woodbury.items():
            before = dict(woodbury.diagnostics)
            release_started = time.perf_counter()
            woodbury.destroy()
            after = dict(woodbury.diagnostics)
            release_records[side]["woodbury"] = {
                "before": before,
                "after": after,
                "release_seconds": _max_elapsed(comm, release_started),
            }
            side_records[side]["woodbury_release"] = release_records[side]["woodbury"]

        for side, fixed in side_fixed.items():
            before = dict(fixed.diagnostics)
            release_started = time.perf_counter()
            fixed.destroy()
            after = dict(fixed.diagnostics)
            release_records[side]["fixed_base"] = {
                "before": before,
                "after": after,
                "release_seconds": _max_elapsed(comm, release_started),
            }
            side_records[side]["fixed_base_release"] = release_records[side][
                "fixed_base"
            ]

        for side, components in side_components.items():
            release_started = time.perf_counter()
            components.destroy()
            release_records[side]["components"] = {
                "destroyed": bool(getattr(components, "_destroyed", False)),
                "release_seconds": _max_elapsed(comm, release_started),
            }

        for side in set(side_actions).intersection(side_oracles):
            direct_action = side_actions[side]
            before = dict(direct_action.diagnostics)
            release_started = time.perf_counter()
            direct_action.destroy()
            after = dict(direct_action.diagnostics)
            release_records[side]["direct_action"] = {
                "before": before,
                "after": after,
                "release_seconds": _max_elapsed(comm, release_started),
            }
            side_records[side]["direct_action_release"] = release_records[side][
                "direct_action"
            ]

        for side, oracle in side_oracles.items():
            release_started = time.perf_counter()
            oracle.destroy()
            release_records[side]["oracle"] = {
                "destroyed": bool(getattr(oracle, "_destroyed", False)),
                "release_seconds": _max_elapsed(comm, release_started),
            }

        for side in ("bottom", "top"):
            if side in side_woodbury:
                release_pass = bool(
                    release_records[side]["woodbury"]["after"].get("destroyed", False)
                    and release_records[side]["fixed_base"]["after"].get(
                        "destroyed", False
                    )
                    and release_records[side]["components"]["destroyed"]
                )
            elif side in side_oracles and side in side_actions:
                release_pass = bool(
                    release_records[side]["direct_action"]["after"].get(
                        "destroyed", False
                    )
                    and release_records[side]["oracle"]["destroyed"]
                )
            else:
                continue
            release_records[side]["release_pass"] = release_pass
            side_records[side]["release_pass"] = release_pass

        outer_rhs_destroy_call_completed = False
        action_matrix_destroy_call_completed = False
        action_context_destroyed = False
        if outer_rhs is not None:
            outer_rhs.destroy()
            outer_rhs_destroy_call_completed = True
        if action_matrix is not None:
            action_matrix.destroy()
            action_matrix_destroy_call_completed = True
        if action_context is not None:
            action_context.destroy()
            action_context_destroyed = bool(
                getattr(action_context, "_destroyed", False)
            )

        outer_release = {
            "outer_rhs_destroy_call_completed": outer_rhs_destroy_call_completed,
            "action_matrix_destroy_call_completed": action_matrix_destroy_call_completed,
            "action_context_destroyed": action_context_destroyed,
            "destroy_calls_complete": bool(
                outer_rhs_destroy_call_completed
                and action_matrix_destroy_call_completed
                and action_context_destroyed
            ),
            "release_seconds": _max_elapsed(comm, v2_release_started),
        }
        release_records["outer"] = outer_release
        if is_v3:
            record_stage("release_finished")

        if record is not None and screen_gate is not None:
            if is_v3:
                record[telemetry_key]["stage_markers"] = list(v3_stage_markers)
            existing_sides = set(side_woodbury) | set(side_oracles)
            release_pass = bool(
                existing_sides == {"bottom", "top"}
                and all(
                    release_records[side].get("release_pass", False)
                    for side in ("bottom", "top")
                )
                and outer_release["destroy_calls_complete"]
                and screen_result is not None
            )
            final_integration_pass = bool(
                record["qualification"]["integration_pass"] and release_pass
            )
            for side in ("bottom", "top"):
                side_records[side]["release_records"] = release_records[side]
            record[telemetry_key]["release_records"] = release_records
            record[telemetry_key]["release_pass"] = release_pass
            if is_v3:
                record[telemetry_key]["v3_release"] = release_pass
            record["timing_seconds_max_rank"][
                "v3_release" if is_v3 else "v2_release"
            ] = float(outer_release["release_seconds"])
            record["timing_seconds_max_rank"]["total"] = _max_elapsed(
                comm, total_started
            )
            record["gates"][f"{gate_prefix}_release"] = release_pass
            record["gates"][f"{gate_prefix}_integration_pass"] = final_integration_pass
            record["qualification"]["integration_pass"] = final_integration_pass
            record["qualification"]["worker_numerical_pass"] = (
                v3_numerical_pass if is_v3 else bool(screen_gate["pass"])
            )
            record["gates"][f"{gate_prefix}_worker_numerical_pass"] = (
                v3_numerical_pass if is_v3 else bool(screen_gate["pass"])
            )
            if not final_integration_pass:
                record["status"] = (
                    "task037b_v3_implementation_gate_failed"
                    if is_v3
                    else "task037b_v2_screen_contract_failed"
                )
                record["qualification"]["disposition"] = (
                    "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
                    if is_v3
                    else "implementation_contract_failed"
                )
            else:
                if is_v3:
                    record["status"] = {
                        "PASS": "task037b_v3_pass",
                        "SLOW": "task037b_v3_slow",
                        "FAMILY_NEGATIVE": "task037b_v3_family_negative",
                    }[v3_classification_code]
                    record["qualification"]["disposition"] = v3_classification
                else:
                    record["status"] = (
                        "task037b_v2_screen_pass"
                        if screen_gate["pass"]
                        else "task037b_v2_screen_numerical_negative"
                    )
                    record["qualification"]["disposition"] = (
                        "screen_pass"
                        if screen_gate["pass"]
                        else "screen_numerical_negative"
                    )

    raise _V3QualificationStop(record) if is_v3 else _V2QualificationStop(record)


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
                timings[f"h5a_{side}_factor"] = _max_elapsed(comm, factor_started)
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
                side_record["solve_seconds"] = _max_elapsed(comm, solve_started)
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
            timings[f"h5a_{side}_release"] = _max_elapsed(comm, release_started)
            side_record["pass"] = bool(
                side_record["rhs"] and all(row["pass"] for row in side_record["rhs"])
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
        timings["h5_post_direct_heap_trim"] = _max_elapsed(comm, heap_trim_started)
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
                h5b_sides[side]["factor_count_before"] for side in ("bottom", "top")
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
                                "solution_digest": _h1_owned_vec_digest(first.solution),
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
                                and first.converged_reason == second.converged_reason
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
                h5b_sides[side]["solve_seconds"] = _max_elapsed(comm, solve_started)
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
                    h5b_sides[side]["configuration"]["no_direct_fallback"] is True
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
        timings["h5b_release_record"] = _max_elapsed(comm, release_started)

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
                "stage4_full3d_assembly_backend": (args.stage4_full3d_assembly_backend),
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
                "h5_no_direct_fallback": (h5_no_direct_fallback),
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


def _run_v1_dtn_component_qualification(
    *,
    args: argparse.Namespace,
    comm: MPI.Intracomm,
    provenance: dict[str, Any],
    authority_gate: dict[str, Any] | None,
    positive,
    negative,
    bottom,
    top,
    coupling,
    timings: dict[str, float],
    total_started: float,
    mark_stage,
    progress,
) -> None:
    """Run the bounded V1 decomposition audit and stop before solver paths."""

    started = time.perf_counter()
    selections = _h5_frozen_mode_selection(positive, negative)
    modal_selections = [
        dict(item)
        for item in selections
        if item["criterion"] == "lowest_propagating_or_lossy"
    ]
    if len(modal_selections) != 2:
        raise RuntimeError("V1 requires one frozen lowest modal probe per direction.")

    def matrix_descriptor(matrix: PETSc.Mat) -> dict[str, Any]:
        first, last = (int(value) for value in matrix.getOwnershipRange())
        global_rows, global_cols = (int(value) for value in matrix.getSize())
        local_rows, local_cols = (int(value) for value in matrix.getLocalSize())
        return {
            "type": str(matrix.getType()),
            "global_size": [global_rows, global_cols],
            "local_size": [local_rows, local_cols],
            "ownership_range": [first, last],
        }

    side_records: dict[str, dict[str, Any]] = {}
    for side, system in (("bottom", bottom), ("top", top)):
        components = create_hybrid_local_dtn_action_components(system)
        component_condition = float(components.h_condition_number)
        component_matrices = {
            "A": matrix_descriptor(system.A),
            "F": matrix_descriptor(components.F),
            "C": matrix_descriptor(components.C),
            "D": matrix_descriptor(components.D),
            "H": matrix_descriptor(components.H),
        }
        component_inventory = dict(system.inventory)
        probes: list[dict[str, Any]] = []

        def audit_probe(name: str, source: PETSc.Vec, metadata: dict[str, Any]) -> None:
            actual = system.A.createVecLeft()
            first = components.F.createVecLeft()
            second = components.F.createVecLeft()
            try:
                system.A.mult(source, actual)
                components.mult(source, first)
                components.mult(source, second)
                action_error = _relative_vector_error(actual, first)
                repeat_error = _relative_vector_error(second, first)
                finite = bool(
                    np.isfinite(action_error)
                    and np.isfinite(repeat_error)
                    and np.isfinite(float(actual.norm()))
                    and np.isfinite(float(first.norm()))
                    and np.isfinite(float(second.norm()))
                )
                probes.append(
                    {
                        "name": name,
                        "metadata": metadata,
                        "source_digest": _h1_owned_vec_digest(source),
                        "component_digest": _h1_owned_vec_digest(first),
                        "action_relative_error": action_error,
                        "component_repeat_relative_error": repeat_error,
                        "finite": finite,
                        "pass": bool(
                            finite
                            and action_error <= 1.0e-11
                            and repeat_error <= 1.0e-12
                        ),
                    }
                )
                progress(
                    f"Task037b V1-R1 {side}/{name}: "
                    f"action={action_error:.3e}, repeat={repeat_error:.3e}"
                )
            finally:
                actual.destroy()
                first.destroy()
                second.destroy()
                source.destroy()

        try:
            audit_probe(
                "physical",
                system.b.copy(),
                {"kind": "physical_action_rhs", "generator": "action_system.b"},
            )
            for seed in (3701, 3702, 3703):
                vector = system.A.createVecRight()
                _h5_fill_partition_independent_random_rhs(vector, seed)
                audit_probe(
                    f"random_seed_{seed}",
                    vector,
                    {
                        "kind": "partition_independent_complex_random",
                        "generator": "indexed_splitmix64_box_muller",
                        "seed": seed,
                        "normalization": "distributed_global_l2",
                    },
                )
            for identity in modal_selections:
                direction = str(identity["direction"])
                mode_index = int(identity["local_mode_index"])
                scaled = (side == "bottom" and direction == "negative") or (
                    side == "top" and direction == "positive"
                )
                propagation = (
                    coupling.propagation.forward
                    if direction == "positive"
                    else coupling.propagation.backward
                )
                scale = (
                    complex(propagation.factors[mode_index]) if scaled else 1.0 + 0.0j
                )
                block = coupling.bottom if side == "bottom" else coupling.top
                audit_probe(
                    f"modal_{direction}_lowest_propagating_or_lossy",
                    _h5_modal_traction_rhs(block, direction, mode_index, scale=scale),
                    {
                        "kind": "frozen_modal_traction",
                        "mode_identity": dict(identity),
                        "propagation_factor": _complex_json(scale),
                    },
                )
            if len(probes) != 6:
                raise RuntimeError("V1 requires exactly six probes per side.")
        finally:
            components.destroy()

        after_source = system.A.createVecRight()
        after_target = system.A.createVecLeft()
        try:
            after_source.set(0.0)
            system.A.mult(after_source, after_target)
            action_usable_after_destroy = bool(np.isfinite(float(after_target.norm())))
        finally:
            after_source.destroy()
            after_target.destroy()
        action_errors = [float(item["action_relative_error"]) for item in probes]
        repeat_errors = [
            float(item["component_repeat_relative_error"]) for item in probes
        ]
        side_records[side] = {
            "h_condition_number": component_condition,
            "matrices": component_matrices,
            "operator_inventory": component_inventory,
            "probes": probes,
            "max_action_relative_error": max(action_errors),
            "max_component_repeat_relative_error": max(repeat_errors),
            "component_destroyed": True,
            "action_usable_after_component_destroy": action_usable_after_destroy,
            "pass": bool(
                all(item["pass"] for item in probes) and action_usable_after_destroy
            ),
        }

    side_pass = {side: bool(item["pass"]) for side, item in side_records.items()}
    r1_pass = bool(len(side_records) == 2 and all(side_pass.values()))
    timings["v1_component_action_audit"] = _max_elapsed(comm, started)
    mark_stage("v1_r1_record")
    _verify_source_stable_at_end(
        comm,
        provenance,
        args.verified_clean_sha,
        args.allow_dirty_research,
    )
    status = (
        "task037b_v1_r1_pass_awaiting_r2"
        if r1_pass
        else "DTN_COMPONENT_DECOMPOSITION_IMPLEMENTATION_FAILED"
    )
    record = {
        "schema_version": 1,
        "record_schema": "task037b.v1-r1-dtn-component-action.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_id": "task037b_v1_dtn_component_action",
        "status": status,
        "metadata": {
            **provenance,
            "command": list(sys.argv),
            "verified_clean_sha": args.verified_clean_sha,
            "authority_gate": authority_gate,
        },
        "case": {
            "degree": args.degree,
            "h_nm": args.h_nm,
            "modal_degree": args.modal_degree,
            "modal_h_nm": args.modal_h_nm,
            "requested_modes": args.requested_modes,
            "candidate_modes": args.candidate_modes,
            "mpi_size": comm.size,
            "polarization_kind": args.polarization_kind,
            "incident_grazing_deg": args.incident_grazing_deg,
            "bottom_interface_nm": args.bottom_interface_nm,
            "top_interface_nm": args.top_interface_nm,
            "solver_path": args.solver_path,
            "formal_modal_probe_selection": modal_selections,
        },
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
            "bottom_operator_inventory": dict(bottom.inventory),
            "top_operator_inventory": dict(top.inventory),
        },
        "v1_telemetry": {
            "task037b_v1_gate": True,
            "r1_scope": "DtN component decomposition only",
            "frozen_mode_selection": selections,
            "formal_modal_probe_selection": modal_selections,
            "formal_probe_count_per_side": 6,
            "sides": side_records,
            "max_action_relative_error": max(
                item["max_action_relative_error"] for item in side_records.values()
            ),
            "max_component_repeat_relative_error": max(
                item["max_component_repeat_relative_error"]
                for item in side_records.values()
            ),
            "ordinary_default_changed": False,
        },
        "gates": {
            "r1_all_probes_finite": bool(
                all(
                    probe["finite"]
                    for side in side_records.values()
                    for probe in side["probes"]
                )
            ),
            "r1_all_action_errors_le_1e-11": bool(
                all(
                    probe["action_relative_error"] <= 1.0e-11
                    for side in side_records.values()
                    for probe in side["probes"]
                )
            ),
            "r1_all_component_repeat_errors_le_1e-12": bool(
                all(
                    probe["component_repeat_relative_error"] <= 1.0e-12
                    for side in side_records.values()
                    for probe in side["probes"]
                )
            ),
            "r1_component_destroy_preserves_action": bool(
                all(
                    side["action_usable_after_component_destroy"]
                    for side in side_records.values()
                )
            ),
            "r1_no_direct_factor": True,
            "r1_pass": r1_pass,
        },
        "qualification": {
            "task037b_v1_gate": True,
            "r1_pass": r1_pass,
            "worker_numerical_pass": r1_pass,
            "integration_pass": r1_pass,
            "disposition": (
                "pass_awaiting_r2"
                if r1_pass
                else "DTN_COMPONENT_DECOMPOSITION_IMPLEMENTATION_FAILED"
            ),
            "boundary": (
                "R1 DtN component decomposition only; R2-R5 not run; "
                "no R/T/A, field, or 12+12 physics Gate."
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
            "R1 component audit does not build a global action or direct factor; "
            "resource samples remain external watchdog evidence."
        ),
    }
    raise _V1QualificationStop(record)


def _run_v1_r2_f_only_qualification(
    *,
    args: argparse.Namespace,
    comm: MPI.Intracomm,
    provenance: dict[str, Any],
    authority_gate: dict[str, Any] | None,
    positive,
    negative,
    bottom,
    top,
    coupling,
    timings: dict[str, float],
    total_started: float,
    mark_stage,
    progress,
) -> None:
    """Run the V1-R2 six-slab diagnostic with the external correction removed."""

    started = time.perf_counter()
    selections = _h5_frozen_mode_selection(positive, negative)
    propagation = coupling.propagation
    rhs_sets: dict[str, list[tuple[str, PETSc.Vec, dict[str, Any]]]] = {
        "bottom": [],
        "top": [],
    }
    bottom_inverse = None
    top_inverse = None
    side_records: dict[str, dict[str, Any]] = {}

    def inverse_contract(inverse) -> dict[str, Any]:
        diagnostics = inverse._diagnostics()
        smoother = diagnostics["smoother"]
        return {
            "operator": dict(diagnostics["operator"]),
            "configuration": dict(diagnostics["configuration"]),
            "smoother": {
                "subdomain_local_diagonal_shift": bool(
                    smoother["subdomain_local_diagonal_shift"]
                ),
                "factor_fingerprints": [
                    dict(fingerprint) for fingerprint in smoother["factor_fingerprints"]
                ],
            },
            "partition_audit": dict(diagnostics["partition_audit"]),
            "source_matrix_nnz": diagnostics["source_matrix_nnz"],
            "factor_nnz": diagnostics["factor_nnz"],
            "factor_csr_payload_estimate_bytes": diagnostics[
                "factor_csr_payload_estimate_bytes"
            ],
            "assembly_payload": dict(diagnostics["assembly_payload"]),
            "no_direct_fallback": bool(diagnostics["no_direct_fallback"]),
            "factor_count_before_destroy": int(
                diagnostics["lifecycle"]["factor_count_before_destroy"]
            ),
        }

    def solve_summary(result) -> dict[str, Any]:
        diagnostics = result.diagnostics
        return {
            "reason": int(result.converged_reason),
            "iterations": int(result.iterations),
            "reported_residual": float(result.reported_relative_residual),
            "f_only_true_residual": float(result.true_relative_residual),
            "stationary_correction_residuals": {
                str(key): float(value)
                for key, value in result.stationary_correction_residuals.items()
            },
            "setup_seconds": float(result.setup_seconds),
            "solve_seconds": float(result.solve_seconds),
            "apply_seconds": float(result.apply_seconds),
            "solution_digest": _h1_owned_vec_digest(result.solution),
            "explicit_true_residual_recomputed": bool(
                diagnostics["explicit_true_residual_recomputed"]
            ),
            "operator_identity": diagnostics["operator"]["identity"],
            "external_dtn_correction": diagnostics["operator"][
                "external_dtn_correction"
            ],
        }

    def result_is_finite(result: dict[str, Any]) -> bool:
        stationary = result["stationary_correction_residuals"]
        return bool(
            all(
                np.isfinite(float(result[key]))
                for key in (
                    "reported_residual",
                    "f_only_true_residual",
                    "setup_seconds",
                    "solve_seconds",
                    "apply_seconds",
                )
            )
            and set(stationary) == {"1", "2", "4", "8"}
            and all(np.isfinite(float(value)) for value in stationary.values())
        )

    def result_pass(result: dict[str, Any]) -> bool:
        return bool(
            result_is_finite(result)
            and result["reason"] > 0
            and result["iterations"] <= H5_MAX_IT
            and result["f_only_true_residual"] <= 1.0e-8
            and result["operator_identity"] == "fine_action_F_only"
            and result["external_dtn_correction"] == "excluded"
            and result["explicit_true_residual_recomputed"]
        )

    try:
        rhs_sets["bottom"] = _h5_rhs_set(
            bottom,
            coupling.bottom,
            selections,
            side="bottom",
            propagation=propagation,
        )
        rhs_sets["top"] = _h5_rhs_set(
            top,
            coupling.top,
            selections,
            side="top",
            propagation=propagation,
        )
        mark_stage("v1_r2_f_only_inverse_setup")
        setup_started = time.perf_counter()
        bottom_inverse = build_hybrid_local_iterative_inverse(
            bottom,
            operator_override=bottom.fine_action,
            operator_identity="fine_action_F_only",
        )
        top_inverse = build_hybrid_local_iterative_inverse(
            top,
            operator_override=top.fine_action,
            operator_identity="fine_action_F_only",
        )
        timings["v1_r2_f_only_inverse_setup"] = _max_elapsed(comm, setup_started)
        inverse_contracts = {
            "bottom": inverse_contract(bottom_inverse),
            "top": inverse_contract(top_inverse),
        }
        mark_stage("v1_r2_f_only_solves")
        for side, inverse in (("bottom", bottom_inverse), ("top", top_inverse)):
            rows: list[dict[str, Any]] = []
            for name, rhs, metadata in rhs_sets[side]:
                source_digest = _h1_owned_vec_digest(rhs)
                first = None
                second = None
                try:
                    first = inverse.solve(rhs)
                    second = inverse.solve(rhs)
                    first_summary = solve_summary(first)
                    second_summary = solve_summary(second)
                    repeat_error = _relative_vector_error(
                        second.solution,
                        first.solution,
                    )
                    row = {
                        "name": name,
                        "metadata": dict(metadata),
                        "source_digest": source_digest,
                        "first": first_summary,
                        "second": second_summary,
                        "repeat_reason_equal": bool(
                            first_summary["reason"] == second_summary["reason"]
                        ),
                        "repeat_iterations_equal": bool(
                            first_summary["iterations"] == second_summary["iterations"]
                        ),
                        "repeat_solution_relative_error": float(repeat_error),
                        "finite": bool(
                            result_is_finite(first_summary)
                            and result_is_finite(second_summary)
                            and np.isfinite(repeat_error)
                        ),
                    }
                    row["pass"] = bool(
                        row["finite"]
                        and result_pass(first_summary)
                        and result_pass(second_summary)
                        and row["repeat_reason_equal"]
                        and row["repeat_iterations_equal"]
                        and repeat_error <= 1.0e-10
                    )
                    progress(
                        f"Task037b V1-R2 {side}/{name}: "
                        f"first_reason={first_summary['reason']}, "
                        f"first_it={first_summary['iterations']}, "
                        f"first_true={first_summary['f_only_true_residual']:.3e}; "
                        f"second_reason={second_summary['reason']}, "
                        f"second_it={second_summary['iterations']}, "
                        f"second_true={second_summary['f_only_true_residual']:.3e}"
                    )
                    rows.append(row)
                finally:
                    if second is not None:
                        second.destroy()
                    if first is not None:
                        first.destroy()
            if len(rows) != 11:
                raise RuntimeError("V1-R2 requires exactly eleven probes per side.")
            side_records[side] = {
                "operator_identity": "fine_action_F_only",
                "external_dtn_correction": "excluded",
                "probe_count": len(rows),
                "probes": rows,
                "max_first_true_residual": max(
                    row["first"]["f_only_true_residual"] for row in rows
                ),
                "max_second_true_residual": max(
                    row["second"]["f_only_true_residual"] for row in rows
                ),
                "max_repeat_solution_relative_error": max(
                    row["repeat_solution_relative_error"] for row in rows
                ),
                "pass": bool(all(row["pass"] for row in rows)),
            }
        no_direct_fallback = bool(
            all(
                contract["no_direct_fallback"]
                for contract in inverse_contracts.values()
            )
            and bottom.inventory.get("direct_factor_count") == 0
            and top.inventory.get("direct_factor_count") == 0
        )
        r2_pass = bool(
            all(side_record["pass"] for side_record in side_records.values())
            and no_direct_fallback
        )
        release_started = time.perf_counter()
        bottom_inverse.destroy()
        bottom_inverse = None
        top_inverse.destroy()
        top_inverse = None
        for side in ("bottom", "top"):
            inverse_contracts[side].update(
                {"factor_count_after_destroy": 0, "factors_released": True}
            )
        timings["v1_r2_f_only_release"] = _max_elapsed(comm, release_started)
        mark_stage("v1_r2_f_only_release")
        mark_stage("v1_r2_f_only_record")
        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        timings["v1_r2_f_only_qualification"] = _max_elapsed(comm, started)
        record = {
            "schema_version": 1,
            "record_schema": "task037b.v1-r2-f-only-local-inverse.v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "benchmark_id": "task037b_v1_r2_f_only_local_inverse",
            "status": "task037b_v1_r2_complete_awaiting_r3",
            "metadata": {
                **provenance,
                "command": list(sys.argv),
                "verified_clean_sha": args.verified_clean_sha,
                "authority_gate": authority_gate,
            },
            "case": {
                "degree": args.degree,
                "h_nm": args.h_nm,
                "modal_degree": args.modal_degree,
                "modal_h_nm": args.modal_h_nm,
                "requested_modes": args.requested_modes,
                "candidate_modes": args.candidate_modes,
                "mpi_size": comm.size,
                "polarization_kind": args.polarization_kind,
                "incident_grazing_deg": args.incident_grazing_deg,
                "bottom_interface_nm": args.bottom_interface_nm,
                "top_interface_nm": args.top_interface_nm,
                "solver_path": args.solver_path,
                "operator_identity": "fine_action_F_only",
                "external_dtn_correction": "excluded",
                "formal_rhs_count_per_side": 11,
            },
            "hybrid_system": {
                "global_action_constructed": False,
                "global_A_materialized": False,
                "global_F_materialized": False,
                "explicit_global_C_D_materialized": False,
                "direct_factor_count": 0,
                "bottom_operator_inventory": dict(bottom.inventory),
                "top_operator_inventory": dict(top.inventory),
            },
            "validation": {
                "port_power": "not_run",
                "R_total": "not_run",
                "T_total": "not_run",
                "A_balance": "not_run",
                "A_volume_total": "not_run",
            },
            "physical_field_reconstruction": {"status": "not_run"},
            "v1_r2_telemetry": {
                "task037b_v1_gate": True,
                "r2_scope": "F-only local operator; external DtN correction excluded",
                "frozen_mode_selection": selections,
                "formal_probe_count_per_side": 11,
                "operator": "borrowed fine_action F_s",
                "external_dtn_correction_excluded": True,
                "sides": side_records,
                "preconditioner": inverse_contracts,
                "ordinary_default_changed": False,
            },
            "gates": {
                "r2_record_complete": True,
                "r2_all_probe_records_complete": bool(
                    all(side["probe_count"] == 11 for side in side_records.values())
                ),
                "r2_all_probes_finite": bool(
                    all(
                        row["finite"]
                        for side in side_records.values()
                        for row in side["probes"]
                    )
                ),
                "r2_no_direct_fallback": no_direct_fallback,
                "r2_pass": r2_pass,
            },
            "qualification": {
                "task037b_v1_gate": True,
                "r2_pass": r2_pass,
                "worker_numerical_pass": r2_pass,
                "integration_pass": True,
                "disposition": (
                    "pass_awaiting_r3"
                    if r2_pass
                    else "F_ONLY_LOCAL_INVERSE_FAMILY_DIAGNOSTIC_NEGATIVE"
                ),
                "boundary": (
                    "R2 F-only six-slab diagnostic complete; R3 whole-endcap test "
                    "awaiting review; no R/T/A, field, or 12+12 physics Gate."
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
                "R2 uses the same six-slab local inverse lifecycle as H5b; "
                "resource samples remain external watchdog evidence."
            ),
        }
        record["gates"]["r2_factors_released"] = True
        raise _V1R2QualificationStop(record)
    finally:
        if bottom_inverse is not None:
            bottom_inverse.destroy()
        if top_inverse is not None:
            top_inverse.destroy()
        for rhs_list in rhs_sets.values():
            for _name, vector, _metadata in rhs_list:
                vector.destroy()


def _run_v1_r4_woodbury_qualification(
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
    timings: dict[str, float],
    total_started: float,
    mark_stage,
    progress,
) -> None:
    """Run the bounded borrowed-base Woodbury R4 diagnostic and stop."""

    started = time.perf_counter()
    selections = _h5_frozen_mode_selection(positive, negative)
    rhs_sets = {
        "bottom": _h5_rhs_set(
            bottom,
            coupling.bottom,
            selections,
            side="bottom",
            propagation=coupling.propagation,
        ),
        "top": _h5_rhs_set(
            top,
            coupling.top,
            selections,
            side="top",
            propagation=coupling.propagation,
        ),
    }
    side_records: dict[str, dict[str, Any]] = {}

    def matrix_descriptor(matrix: PETSc.Mat) -> dict[str, Any]:
        first, last = matrix.getOwnershipRange()
        return {
            "type": str(matrix.getType()),
            "shape": [int(value) for value in matrix.getSize()],
            "local_shape": [int(value) for value in matrix.getLocalSize()],
            "ownership_range": [int(first), int(last)],
        }

    def finite_row(row: dict[str, Any]) -> bool:
        values = (
            row["direct_true_residual"],
            row["woodbury_true_residual"],
            row["solution_relative_error"],
            row["repeat_error"],
        )
        return bool(all(np.isfinite(float(value)) for value in values))

    for side, action_system in (("bottom", bottom), ("top", top)):
        direct_system = None
        blocks = None
        explicit_a = None
        explicit_port = None
        explicit_f = None
        a_factor = None
        f_factor = None
        components = None
        oracle = None
        component_descriptors: dict[str, Any] = {}
        active_factor_count = 0
        max_active_factor_count = 0
        a_released_before_f_created = False
        explicit_reference_blocks_released = False
        direct_solutions: dict[str, PETSc.Vec] = {}
        side_started = time.perf_counter()
        try:
            mark_stage(f"v1_r4_{side}_explicit_a_assembly")
            assembly_started = time.perf_counter()
            direct_system = assemble_hybrid_local_dtn_system(
                cfg,
                side,
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
                local_mesh_override=action_system.local_mesh,
                log=progress,
            )
            blocks = extract_petsc_condensed_blocks(
                direct_system.A,
                direct_system.b,
                n_fe=direct_system.n_fe,
                n_aux=direct_system.n_external_aux,
            )
            if blocks.n_aux != R4_MODAL_COUNT:
                raise RuntimeError("R4 direct reference must expose 40 auxiliary modes")
            explicit_a, explicit_port = build_explicit_condensed_operator(blocks)
            direct_system.destroy()
            direct_system = None
            timings[f"v1_r4_{side}_explicit_a_assembly"] = _max_elapsed(
                comm, assembly_started
            )

            mark_stage(f"v1_r4_{side}_a_factor")
            a_factor_started = time.perf_counter()
            a_factor, a_setup_seconds = _factor_local(explicit_a)
            active_factor_count += 1
            max_active_factor_count = max(max_active_factor_count, active_factor_count)
            a_factor_count_before = active_factor_count
            a_inventory = _local_factor_inventory(a_factor)
            timings[f"v1_r4_{side}_a_factor"] = _max_elapsed(comm, a_factor_started)
            mark_stage(f"v1_r4_{side}_a_reference_solve")
            a_solve_started = time.perf_counter()
            a_rows: list[dict[str, Any]] = []
            for name, rhs, metadata in rhs_sets[side]:
                reference = rhs.duplicate()
                a_factor.solve(rhs, reference)
                direct_solutions[name] = reference
                a_rows.append(
                    {
                        "name": name,
                        "metadata": dict(metadata),
                        "source_digest": _h1_owned_vec_digest(rhs),
                        "direct_true_residual": _h5_true_relative_residual(
                            explicit_a, rhs, reference
                        ),
                        "solution_digest": _h1_owned_vec_digest(reference),
                    }
                )
            timings[f"v1_r4_{side}_a_reference_solve"] = _max_elapsed(
                comm, a_solve_started
            )
            a_release_started = time.perf_counter()
            a_factor.destroy()
            a_factor = None
            active_factor_count -= 1
            a_factor_count_after_release = active_factor_count
            a_release_seconds = _max_elapsed(comm, a_release_started)
            explicit_a.destroy()
            explicit_a = None
            explicit_port.destroy()
            explicit_port = None
            a_released_before_f_created = active_factor_count == 0
            explicit_f = blocks.require_f()
            blocks.F = None
            blocks.destroy()
            blocks = None
            explicit_reference_blocks_released = (
                blocks is None and explicit_f is not None
            )

            mark_stage(f"v1_r4_{side}_f_factor")
            f_factor_started = time.perf_counter()
            f_factor, f_setup_seconds = _factor_local(explicit_f)
            active_factor_count += 1
            max_active_factor_count = max(max_active_factor_count, active_factor_count)
            f_factor_count_before = active_factor_count
            f_inventory = _local_factor_inventory(f_factor)
            timings[f"v1_r4_{side}_f_factor"] = _max_elapsed(comm, f_factor_started)
            components = create_hybrid_local_dtn_action_components(action_system)
            component_descriptors = {
                "F": matrix_descriptor(components.F),
                "C": matrix_descriptor(components.C),
                "D": matrix_descriptor(components.D),
                "H": matrix_descriptor(components.H),
            }
            oracle_started = time.perf_counter()
            oracle = HybridLocalDtnWoodburyOracle(
                f_factor,
                components,
                base_identity="exact_F_direct_test_only",
            )
            timings[f"v1_r4_{side}_woodbury_setup"] = _max_elapsed(comm, oracle_started)
            mark_stage(f"v1_r4_{side}_woodbury_solve")
            solve_started = time.perf_counter()
            woodbury_rows: list[dict[str, Any]] = []
            for a_row, (name, rhs, metadata) in zip(
                a_rows,
                rhs_sets[side],
                strict=True,
            ):
                first = rhs.duplicate()
                second = rhs.duplicate()
                try:
                    oracle.apply(rhs, first)
                    oracle.apply(rhs, second)
                    woodbury_diagnostics = oracle.diagnostics
                    row = {
                        **a_row,
                        "name": name,
                        "metadata": dict(metadata),
                        "woodbury_true_residual": _h5_true_relative_residual(
                            action_system.A, rhs, first
                        ),
                        "solution_relative_error": _relative_vector_error(
                            first, direct_solutions[name]
                        ),
                        "repeat_error": _relative_vector_error(first, second),
                        "solution_digest": _h1_owned_vec_digest(first),
                        "zero_physical_rhs": bool(float(rhs.norm()) <= 1.0e-30),
                    }
                    row["finite"] = finite_row(row)
                    row["pass"] = bool(
                        row["finite"]
                        and row["direct_true_residual"] <= 1.0e-10
                        and row["woodbury_true_residual"] <= 1.0e-10
                        and row["solution_relative_error"] <= 1.0e-10
                        and row["repeat_error"] <= 1.0e-12
                        and woodbury_diagnostics["K_rank"] == R4_MODAL_COUNT
                        and woodbury_diagnostics["K_condition_number"] <= 1.0e10
                    )
                    progress(
                        f"Task037b V1-R4 {side}/{name}: "
                        f"woodbury={row['woodbury_true_residual']:.3e}, "
                        f"solution={row['solution_relative_error']:.3e}, "
                        f"repeat={row['repeat_error']:.3e}"
                    )
                    woodbury_rows.append(row)
                finally:
                    first.destroy()
                    second.destroy()
            timings[f"v1_r4_{side}_woodbury_solve"] = _max_elapsed(comm, solve_started)
            woodbury_diagnostics = oracle.diagnostics
            local_w_bytes = int(woodbury_diagnostics["W_local_nbytes"])
            w_bytes_by_rank = [int(value) for value in comm.allgather(local_w_bytes)]
            woodbury_diagnostics.update(
                {
                    "W_local_nbytes_by_rank": w_bytes_by_rank,
                    "W_local_nbytes_sum": int(sum(w_bytes_by_rank)),
                    "W_local_nbytes_max": int(max(w_bytes_by_rank)),
                    "K_replicated_per_rank_nbytes": int(
                        woodbury_diagnostics["K_nbytes"]
                    ),
                    "LU_replicated_per_rank_nbytes": int(
                        woodbury_diagnostics["LU_nbytes"]
                    ),
                }
            )
            oracle.destroy()
            oracle = None
            components.destroy()
            components = None
            zero = action_system.A.createVecRight()
            zero_result = action_system.A.createVecLeft()
            try:
                zero.set(0.0)
                action_system.A.mult(zero, zero_result)
                action_survives_after_release = bool(
                    action_system.A.getType() == "python"
                    and np.isfinite(float(zero_result.norm()))
                )
            finally:
                zero_result.destroy()
                zero.destroy()
            f_release_started = time.perf_counter()
            f_factor.destroy()
            f_factor = None
            active_factor_count -= 1
            f_release_seconds = _max_elapsed(comm, f_release_started)
            f_factor_count_after_release = active_factor_count
            explicit_f.destroy()
            explicit_f = None
            final_active_factor_count = f_factor_count_after_release
            factor_release = {
                "a_factor": {
                    "factor_count_before": a_factor_count_before,
                    "factor_count_after": a_factor_count_after_release,
                    "inventory": a_inventory,
                    "released": True,
                    "setup_seconds": float(a_setup_seconds),
                    "release_seconds": float(a_release_seconds),
                },
                "f_factor": {
                    "factor_count_before": f_factor_count_before,
                    "factor_count_after": f_factor_count_after_release,
                    "inventory": f_inventory,
                    "released": True,
                    "setup_seconds": float(f_setup_seconds),
                    "release_seconds": float(f_release_seconds),
                },
                "a_released_before_f_created": a_released_before_f_created,
                "max_active_factor_count": max_active_factor_count,
                "final_active_factor_count": final_active_factor_count,
                "never_simultaneous": bool(
                    a_released_before_f_created
                    and max_active_factor_count == 1
                    and final_active_factor_count == 0
                ),
                "explicit_reference_C_D_H_released_before_f_factor": (
                    explicit_reference_blocks_released
                ),
            }
            nonzero_rows = [
                row for row in woodbury_rows if not row["zero_physical_rhs"]
            ]
            zero_rows = [row for row in woodbury_rows if row["zero_physical_rhs"]]
            expected_nonzero = 10 if side == "bottom" else 11
            for row in nonzero_rows:
                row["capacity_pass"] = bool(row["pass"])
            for row in zero_rows:
                row["zero_equation_pass"] = bool(row["pass"])
            capacity_pass_count = sum(
                bool(row["capacity_pass"]) for row in nonzero_rows
            )
            zero_equation_pass = bool(
                len(zero_rows) == (1 if side == "bottom" else 0)
                and all(row.get("zero_equation_pass") is True for row in zero_rows)
            )
            side_contract_pass = bool(
                len(woodbury_rows) == 11
                and len(nonzero_rows) == expected_nonzero
                and len(zero_rows) == (1 if side == "bottom" else 0)
                and action_survives_after_release
                and factor_release["never_simultaneous"]
                and factor_release["max_active_factor_count"] == 1
                and factor_release["final_active_factor_count"] == 0
                and factor_release["explicit_reference_C_D_H_released_before_f_factor"]
            )
            side_numerical_pass = bool(
                side_contract_pass
                and capacity_pass_count == expected_nonzero
                and zero_equation_pass
                and all(row["pass"] for row in woodbury_rows)
            )
            side_records[side] = {
                "operator": {
                    "identity": "borrowed_F_plus_Dtn_Woodbury",
                    "base_identity": "exact_F_direct_test_only",
                    "external_dtn_correction": "included",
                    "normal_equations": False,
                    "n_aux": R4_MODAL_COUNT,
                    "components": component_descriptors,
                },
                "rows": woodbury_rows,
                "probe_count": len(woodbury_rows),
                "direct_reference_rows": a_rows,
                "woodbury": dict(woodbury_diagnostics),
                "factor_release": factor_release,
                "action_survives_after_release": action_survives_after_release,
                "nonzero_capacity_count": len(nonzero_rows),
                "capacity_pass_count": int(capacity_pass_count),
                "capacity_expected_count": expected_nonzero,
                "zero_physical_count": len(zero_rows),
                "zero_equation_pass": zero_equation_pass,
                "contract_pass": side_contract_pass,
                "all_probes_finite": bool(all(row["finite"] for row in woodbury_rows)),
                "pass": side_numerical_pass,
                "wall_seconds": _max_elapsed(comm, side_started),
            }
            for reference in direct_solutions.values():
                reference.destroy()
            direct_solutions.clear()
        finally:
            if oracle is not None:
                oracle.destroy()
            if components is not None:
                components.destroy()
            if f_factor is not None:
                f_factor.destroy()
                active_factor_count = max(active_factor_count - 1, 0)
            if explicit_f is not None:
                explicit_f.destroy()
            if a_factor is not None:
                a_factor.destroy()
            if explicit_port is not None:
                explicit_port.destroy()
            if explicit_a is not None:
                explicit_a.destroy()
            if blocks is not None:
                blocks.destroy()
            if direct_system is not None:
                direct_system.destroy()
            for reference in direct_solutions.values():
                reference.destroy()

    r4_contract_pass = bool(
        set(side_records) == {"bottom", "top"}
        and all(
            side_record["probe_count"] == 11
            and side_record["nonzero_capacity_count"]
            == (10 if side_name == "bottom" else 11)
            and side_record["zero_physical_count"]
            == (1 if side_name == "bottom" else 0)
            and side_record["contract_pass"] is True
            and side_record["action_survives_after_release"] is True
            and side_record["factor_release"]["never_simultaneous"] is True
            and side_record["factor_release"]["max_active_factor_count"] == 1
            and side_record["factor_release"]["final_active_factor_count"] == 0
            and side_record["factor_release"][
                "explicit_reference_C_D_H_released_before_f_factor"
            ]
            is True
            and all(
                factor["factor_count_before"] == 1
                and factor["factor_count_after"] == 0
                and factor["released"] is True
                for factor in side_record["factor_release"].values()
                if isinstance(factor, dict) and "factor_count_before" in factor
            )
            for side_name, side_record in side_records.items()
        )
    )
    r4_numerical_pass = bool(
        r4_contract_pass
        and all(side_record["pass"] for side_record in side_records.values())
    )
    timings["v1_r4_woodbury_qualification"] = _max_elapsed(comm, started)
    mark_stage("v1_r4_record")
    _verify_source_stable_at_end(
        comm,
        provenance,
        args.verified_clean_sha,
        args.allow_dirty_research,
    )
    record = {
        "schema_version": 1,
        "record_schema": "task037b.v1-r4-dtn-woodbury.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_id": "task037b_v1_r4_dtn_woodbury_oracle",
        "status": (
            "task037b_v1_r4_complete_awaiting_r5"
            if r4_numerical_pass
            else "DTN_WOODBURY_ORACLE_IMPLEMENTATION_FAILED"
        ),
        "metadata": {
            **provenance,
            "command": list(sys.argv),
            "verified_clean_sha": args.verified_clean_sha,
            "authority_gate": authority_gate,
        },
        "case": {
            "degree": args.degree,
            "h_nm": args.h_nm,
            "modal_degree": args.modal_degree,
            "modal_h_nm": args.modal_h_nm,
            "requested_modes": args.requested_modes,
            "candidate_modes": args.candidate_modes,
            "mpi_size": comm.size,
            "polarization_kind": args.polarization_kind,
            "incident_grazing_deg": args.incident_grazing_deg,
            "bottom_interface_nm": args.bottom_interface_nm,
            "top_interface_nm": args.top_interface_nm,
            "solver_path": args.solver_path,
            "operator_identity": "borrowed_F_plus_Dtn_Woodbury",
            "formal_rhs_count_per_side": 11,
        },
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
            "external_auxiliary_rows_in_krylov": 0,
            "bottom_operator_inventory": dict(bottom.inventory),
            "top_operator_inventory": dict(top.inventory),
        },
        "validation": {
            "port_power": "not_run",
            "R_total": "not_run",
            "T_total": "not_run",
            "A_balance": "not_run",
            "A_volume_total": "not_run",
            "external_diffraction_orders": "not_run",
        },
        "physical_field_reconstruction": {"status": "not_run"},
        "official_record": False,
        "v1_r4_telemetry": {
            "task037b_v1_gate": True,
            "r4_scope": "borrowed-base 40-mode Woodbury exact action",
            "formula": "A=F-C H^-1 D; W=F^-1 C; K=H-DW",
            "n_aux": R4_MODAL_COUNT,
            "normal_equations": False,
            "frozen_mode_selection": selections,
            "formal_probe_count_per_side": 11,
            "sides": side_records,
            "r4_contract_pass": r4_contract_pass,
            "r4_numerical_pass": r4_numerical_pass,
            "ordinary_default_changed": False,
        },
        "gates": {
            "r4_record_complete": r4_contract_pass,
            "r4_all_probe_records_complete": bool(
                all(side["probe_count"] == 11 for side in side_records.values())
            ),
            "r4_all_probes_finite": bool(
                all(
                    row["finite"]
                    for side in side_records.values()
                    for row in side["rows"]
                )
            ),
            "r4_factor_noncoexistence": bool(
                all(
                    side["factor_release"]["never_simultaneous"]
                    for side in side_records.values()
                )
            ),
            "r4_factors_released": bool(
                all(
                    factor["factor_count_after"] == 0 and factor["released"] is True
                    for side in side_records.values()
                    for factor in (
                        side["factor_release"]["a_factor"],
                        side["factor_release"]["f_factor"],
                    )
                )
            ),
            "r4_no_direct_fallback": bool(
                all(
                    side["factor_release"]["never_simultaneous"]
                    and side["action_survives_after_release"]
                    for side in side_records.values()
                )
            ),
            "r4_pass": r4_numerical_pass,
        },
        "qualification": {
            "task037b_v1_gate": True,
            "r4_pass": r4_numerical_pass,
            "worker_numerical_pass": r4_numerical_pass,
            "integration_pass": r4_numerical_pass,
            "disposition": (
                "r4_pass_awaiting_r5"
                if r4_numerical_pass
                else "DTN_WOODBURY_ORACLE_IMPLEMENTATION_FAILED"
            ),
            "boundary": (
                "R4 Woodbury oracle only; R5 and R/T/A, field, and 12+12 "
                "physics gates are not run."
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
            "R4 explicit A and F factors are sequential test-only references; "
            "the global Hybrid action remains unmaterialized."
        ),
    }
    raise _V1R4QualificationStop(record)


def _run_v1_r5_local_inverse_qualification(
    *,
    args: argparse.Namespace,
    comm: MPI.Intracomm,
    provenance: dict[str, Any],
    authority_gate: dict[str, Any] | None,
    positive: Any,
    negative: Any,
    bottom: Any,
    top: Any,
    coupling: Any,
    timings: dict[str, float],
    total_started: float,
    mark_stage,
    progress,
) -> None:
    """Run the fixed whole-endcap smoother Woodbury R5 candidate."""

    started = time.perf_counter()
    selections = _h5_frozen_mode_selection(positive, negative)
    rhs_sets = {
        "bottom": _h5_rhs_set(
            bottom,
            coupling.bottom,
            selections,
            side="bottom",
            propagation=coupling.propagation,
        ),
        "top": _h5_rhs_set(
            top,
            coupling.top,
            selections,
            side="top",
            propagation=coupling.propagation,
        ),
    }
    side_records: dict[str, dict[str, Any]] = {}

    rhs_released = False

    def release_rhs_sets() -> None:
        nonlocal rhs_released
        if rhs_released:
            return
        for rhs_list in rhs_sets.values():
            for _name, vector, _metadata in rhs_list:
                vector.destroy()
        rhs_released = True

    bottom_released_before_top_setup = False
    global_max_active_factor_count = 0
    global_final_active_factor_count = 0

    def result_summary(result: Any) -> dict[str, Any]:
        diagnostics = result.diagnostics
        return {
            "reason": int(result.converged_reason),
            "iterations": int(result.iterations),
            "reported_residual": float(result.reported_relative_residual),
            "complete_A_true_residual": float(result.true_relative_residual),
            "setup_seconds": float(result.setup_seconds),
            "solve_seconds": float(result.solve_seconds),
            "apply_seconds": float(result.apply_seconds),
            "solution_digest": _h1_owned_vec_digest(result.solution),
            "explicit_true_residual_recomputed": bool(
                diagnostics["explicit_complete_action_residual_recomputed"]
            ),
        }

    def summary_finite(summary: dict[str, Any]) -> bool:
        return bool(
            all(
                np.isfinite(float(summary[key]))
                for key in (
                    "reported_residual",
                    "complete_A_true_residual",
                    "setup_seconds",
                    "solve_seconds",
                    "apply_seconds",
                )
            )
            and summary["reason"] == int(summary["reason"])
            and summary["iterations"] == int(summary["iterations"])
        )

    for side, action_system in (("bottom", bottom), ("top", top)):
        base_inverse = None
        inverse = None
        side_started = time.perf_counter()
        try:
            if side == "top":
                bottom_release = side_records["bottom"]["factor_release"]
                bottom_released_before_top_setup = bool(
                    bottom_release["factor_count_after"] == 0
                    and bottom_release["factors_released"] is True
                )
            mark_stage(f"v1_r5_{side}_setup")
            setup_started = time.perf_counter()
            base_inverse = build_hybrid_local_iterative_inverse(
                action_system,
                preconditioner_profile=R3_PRECONDITIONER_PROFILE,
            )
            inverse = build_hybrid_local_dtn_woodbury_local_inverse(
                action_system,
                base_inverse,
            )
            timings[f"v1_r5_{side}_setup"] = _max_elapsed(comm, setup_started)
            preconditioner = inverse.diagnostics
            mark_stage(f"v1_r5_{side}_solves")
            solve_started = time.perf_counter()
            rows: list[dict[str, Any]] = []
            for name, rhs, metadata in rhs_sets[side]:
                first = None
                second = None
                try:
                    first = inverse.solve(rhs)
                    second = inverse.solve(rhs)
                    first_summary = result_summary(first)
                    second_summary = result_summary(second)
                    repeat_error = _relative_vector_error(
                        first.solution, second.solution
                    )
                    row = {
                        "name": name,
                        "metadata": dict(metadata),
                        "source_digest": _h1_owned_vec_digest(rhs),
                        "first": first_summary,
                        "second": second_summary,
                        "repeat_reason_equal": bool(
                            first_summary["reason"] == second_summary["reason"]
                        ),
                        "repeat_iterations_equal": bool(
                            first_summary["iterations"] == second_summary["iterations"]
                        ),
                        "repeat_solution_relative_error": float(repeat_error),
                        "zero_physical_rhs": bool(float(rhs.norm()) <= 1.0e-30),
                    }
                    row["finite"] = bool(
                        summary_finite(first_summary)
                        and summary_finite(second_summary)
                        and np.isfinite(repeat_error)
                    )
                    row["pass"] = bool(
                        row["finite"]
                        and first_summary["reason"] > 0
                        and second_summary["reason"] > 0
                        and first_summary["iterations"] <= H5_MAX_IT
                        and second_summary["iterations"] <= H5_MAX_IT
                        and first_summary["complete_A_true_residual"] <= 1.0e-8
                        and second_summary["complete_A_true_residual"] <= 1.0e-8
                        and repeat_error <= 1.0e-12
                    )
                    progress(
                        f"Task037b V1-R5 {side}/{name}: "
                        f"first_reason={first_summary['reason']}, "
                        f"first_it={first_summary['iterations']}, "
                        f"first_true={first_summary['complete_A_true_residual']:.3e}; "
                        f"second_reason={second_summary['reason']}, "
                        f"second_it={second_summary['iterations']}, "
                        f"second_true={second_summary['complete_A_true_residual']:.3e}"
                    )
                    rows.append(row)
                finally:
                    if second is not None:
                        second.destroy()
                    if first is not None:
                        first.destroy()
            timings[f"v1_r5_{side}_solves"] = _max_elapsed(comm, solve_started)

            nonzero_indices = [
                index
                for index, item in enumerate(rhs_sets[side])
                if float(item[1].norm()) > 1.0e-30
            ]
            if len(nonzero_indices) < 2:
                raise RuntimeError("R5 requires two nonzero probes for PC audit")
            first_rhs = rhs_sets[side][nonzero_indices[0]][1]
            second_rhs = rhs_sets[side][nonzero_indices[1]][1]
            pc_first = action_system.A.createVecLeft()
            pc_second = action_system.A.createVecLeft()
            pc_repeat = action_system.A.createVecLeft()
            pc_lhs = action_system.A.createVecLeft()
            pc_rhs = action_system.A.createVecLeft()
            combined_rhs = action_system.A.createVecRight()
            try:
                alpha = PETSc.ScalarType(1.25)
                beta = PETSc.ScalarType(-0.75)
                inverse.woodbury.apply(first_rhs, pc_first)
                inverse.woodbury.apply(second_rhs, pc_second)
                inverse.woodbury.apply(first_rhs, pc_repeat)
                first_rhs.copy(combined_rhs)
                combined_rhs.scale(alpha)
                combined_rhs.axpy(beta, second_rhs)
                inverse.woodbury.apply(combined_rhs, pc_lhs)
                pc_first.copy(pc_rhs)
                pc_rhs.scale(alpha)
                pc_rhs.axpy(beta, pc_second)
                pc_linearity_error = _relative_vector_error(pc_lhs, pc_rhs)
                pc_determinism_error = _relative_vector_error(pc_first, pc_repeat)
            finally:
                combined_rhs.destroy()
                pc_rhs.destroy()
                pc_lhs.destroy()
                pc_repeat.destroy()
                pc_second.destroy()
                pc_first.destroy()

            # Refresh after all solves and PC probes so apply counters/timing
            # and the stored global arrays_finite evidence are not stale.
            preconditioner = inverse.diagnostics
            woodbury = dict(preconditioner["woodbury"])
            local_w_bytes = int(woodbury["W_local_nbytes"])
            w_bytes_by_rank = [int(value) for value in comm.allgather(local_w_bytes)]
            woodbury.update(
                {
                    "W_local_nbytes_by_rank": w_bytes_by_rank,
                    "W_local_nbytes_sum": int(sum(w_bytes_by_rank)),
                    "W_local_nbytes_max": int(max(w_bytes_by_rank)),
                    "K_replicated_per_rank_nbytes": int(woodbury["K_nbytes"]),
                    "LU_replicated_per_rank_nbytes": int(woodbury["LU_nbytes"]),
                }
            )
            preconditioner["woodbury"] = woodbury
            preconditioner["pc_audit"] = {
                "linearity_error": float(pc_linearity_error),
                "determinism_error": float(pc_determinism_error),
                "finite": bool(
                    np.isfinite(pc_linearity_error)
                    and np.isfinite(pc_determinism_error)
                ),
            }

            mark_stage(f"v1_r5_{side}_release")
            released_inverse = inverse
            inverse = None
            release_started = time.perf_counter()
            released_inverse.destroy()
            timings[f"v1_r5_{side}_release"] = _max_elapsed(comm, release_started)
            factor_before = released_inverse.factor_count_before_destroy
            factor_after = released_inverse.factor_count_after_destroy
            factors_released = released_inverse.factors_released
            woodbury_destroyed = released_inverse.woodbury.diagnostics["destroyed"]
            global_max_active_factor_count = max(
                global_max_active_factor_count, int(factor_before)
            )
            global_final_active_factor_count = int(factor_after)
            action_survives = False
            zero = action_system.A.createVecRight()
            zero_result = action_system.A.createVecLeft()
            try:
                zero.set(0.0)
                action_system.A.mult(zero, zero_result)
                action_survives = bool(
                    action_system.A.getType() == "python"
                    and np.isfinite(float(zero_result.norm()))
                )
            finally:
                zero_result.destroy()
                zero.destroy()
            base_inverse = None
            nonzero_rows = [row for row in rows if not row["zero_physical_rhs"]]
            zero_rows = [row for row in rows if row["zero_physical_rhs"]]
            expected_nonzero = 10 if side == "bottom" else 11
            for row in nonzero_rows:
                row["capacity_pass"] = bool(row["pass"])
            for row in zero_rows:
                row["zero_equation_pass"] = bool(row["pass"])
            capacity_pass_count = sum(
                bool(row["capacity_pass"]) for row in nonzero_rows
            )
            zero_equation_pass = bool(
                len(zero_rows) == (1 if side == "bottom" else 0)
                and all(row.get("zero_equation_pass") is True for row in zero_rows)
            )
            side_contract_pass = bool(
                len(rows) == 11
                and len(nonzero_rows) == expected_nonzero
                and len(zero_rows) == (1 if side == "bottom" else 0)
                and preconditioner["operator"]["identity"]
                == "complete_hybrid_action_with_whole_endcap_dtn_woodbury"
                and preconditioner["configuration"]["preconditioner_profile"]
                == R3_PRECONDITIONER_PROFILE
                and preconditioner["configuration"]["num_subdomains"] == 1
                and preconditioner["configuration"]["overlap_fraction"] == 0.0
                and preconditioner["lifecycle"]["candidate_direct_factor_count"] == 0
                and factor_before == 1
                and factor_after == 0
                and factors_released is True
                and woodbury_destroyed is True
                and action_survives
            )
            algebra_legality_pass = bool(
                all(row["finite"] for row in rows)
                and all(
                    row["repeat_solution_relative_error"] <= 1.0e-12 for row in rows
                )
                and preconditioner["no_direct_fallback"] is True
                and woodbury["K_rank"] == R4_MODAL_COUNT
                and np.isfinite(woodbury["K_condition_number"])
                and woodbury["K_condition_number"] <= 1.0e10
                and woodbury["normal_equations"] is False
                and woodbury["arrays_finite"] is True
                and preconditioner["pc_audit"]["finite"]
                and pc_linearity_error <= 1.0e-11
                and pc_determinism_error <= 1.0e-12
            )
            side_numerical_pass = bool(
                side_contract_pass
                and algebra_legality_pass
                and capacity_pass_count == expected_nonzero
                and zero_equation_pass
                and all(row["pass"] for row in rows)
                and pc_linearity_error <= 1.0e-11
                and pc_determinism_error <= 1.0e-12
            )
            side_records[side] = {
                "operator": dict(preconditioner["operator"]),
                "configuration": dict(preconditioner["configuration"]),
                "base": dict(preconditioner["base"]),
                "woodbury": woodbury,
                "pc_audit": dict(preconditioner["pc_audit"]),
                "algebra_legality_pass": algebra_legality_pass,
                "rows": rows,
                "probe_count": len(rows),
                "nonzero_capacity_count": len(nonzero_rows),
                "capacity_pass_count": int(capacity_pass_count),
                "capacity_expected_count": expected_nonzero,
                "zero_physical_count": len(zero_rows),
                "zero_equation_pass": zero_equation_pass,
                "factor_release": {
                    "factor_count_before": int(factor_before),
                    "factor_count_after": int(factor_after),
                    "factors_released": bool(factors_released),
                    "woodbury_destroyed": bool(woodbury_destroyed),
                    "max_active_factor_count": int(factor_before),
                    "never_simultaneous": bool(factor_before == 1),
                },
                "action_survives_after_release": bool(action_survives),
                "no_direct_fallback": bool(
                    preconditioner["no_direct_fallback"]
                    and preconditioner["operator"]["direct_factor_count"] == 0
                ),
                "contract_pass": side_contract_pass,
                "all_probes_finite": bool(all(row["finite"] for row in rows)),
                "pass": side_numerical_pass,
                "wall_seconds": _max_elapsed(comm, side_started),
            }
        except Exception:
            release_rhs_sets()
            raise
        finally:
            if inverse is not None:
                inverse.destroy()
                base_inverse = None
            if base_inverse is not None:
                base_inverse.destroy()

    r5_contract_pass = bool(
        set(side_records) == {"bottom", "top"}
        and all(side["contract_pass"] for side in side_records.values())
        and bottom_released_before_top_setup
        and global_max_active_factor_count == 1
        and global_final_active_factor_count == 0
    )
    r5_algebra_legality_pass = bool(
        r5_contract_pass
        and all(
            side["algebra_legality_pass"]
            and side["pc_audit"]["linearity_error"] <= 1.0e-11
            and side["pc_audit"]["determinism_error"] <= 1.0e-12
            for side in side_records.values()
        )
    )
    r5_numerical_pass = bool(
        r5_algebra_legality_pass and all(side["pass"] for side in side_records.values())
    )

    def row_residual(row: dict[str, Any]) -> float:
        return max(
            float(row["first"]["complete_A_true_residual"]),
            float(row["second"]["complete_A_true_residual"]),
        )

    all_random_values: list[float] = []
    all_modal_values: list[float] = []
    all_iterations_ok = True
    all_rows_finite = True
    severe_negative = False
    for side in side_records.values():
        random_rows = [
            row
            for row in side["rows"]
            if row["metadata"].get("kind") == "partition_independent_complex_random"
        ]
        modal_or_physical_rows = [
            row
            for row in side["rows"]
            if row["metadata"].get("kind")
            in {"physical_action_rhs", "frozen_modal_traction"}
        ]
        random_values = [row_residual(row) for row in random_rows]
        modal_values = [row_residual(row) for row in modal_or_physical_rows]
        all_random_values.extend(random_values)
        all_modal_values.extend(modal_values)
        all_iterations_ok &= all(
            summary["iterations"] <= H5_MAX_IT
            for row in side["rows"]
            for summary in (row["first"], row["second"])
        )
        all_rows_finite &= side["all_probes_finite"]
        severe_negative |= bool(
            sum(value > 1.0e-2 for value in random_values) > len(random_values) / 2
            or any(value > 1.0e-3 for value in modal_values)
        )
    r5_borderline = bool(
        not r5_numerical_pass
        and r5_contract_pass
        and r5_algebra_legality_pass
        and all_modal_values
        and all_random_values
        and all(value <= 1.0e-8 for value in all_modal_values)
        and all(value <= 1.0e-5 for value in all_random_values)
        and any(value > 1.0e-8 for value in all_random_values)
        and all_iterations_ok
        and all_rows_finite
    )
    timings["v1_r5_local_inverse_qualification"] = _max_elapsed(comm, started)
    mark_stage("v1_r5_record")
    _verify_source_stable_at_end(
        comm,
        provenance,
        args.verified_clean_sha,
        args.allow_dirty_research,
    )
    status = (
        "task037b_v1_r5_complete_awaiting_h6"
        if r5_numerical_pass
        else "DTN_WOODBURY_LOCAL_INVERSE_BORDERLINE"
        if r5_borderline
        else "WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE"
        if r5_contract_pass
        else "DTN_WOODBURY_LOCAL_INVERSE_IMPLEMENTATION_FAILED"
    )
    record = {
        "schema_version": 1,
        "record_schema": "task037b.v1-r5-dtn-woodbury-local-inverse.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_id": "task037b_v1_r5_dtn_woodbury_local_inverse",
        "status": status,
        "metadata": {
            **provenance,
            "command": list(sys.argv),
            "verified_clean_sha": args.verified_clean_sha,
            "authority_gate": authority_gate,
        },
        "case": {
            "degree": args.degree,
            "h_nm": args.h_nm,
            "modal_degree": args.modal_degree,
            "modal_h_nm": args.modal_h_nm,
            "requested_modes": args.requested_modes,
            "candidate_modes": args.candidate_modes,
            "mpi_size": comm.size,
            "polarization_kind": args.polarization_kind,
            "incident_grazing_deg": args.incident_grazing_deg,
            "bottom_interface_nm": args.bottom_interface_nm,
            "top_interface_nm": args.top_interface_nm,
            "solver_path": args.solver_path,
            "operator_identity": (
                "complete_hybrid_action_with_whole_endcap_dtn_woodbury"
            ),
            "formal_probe_count_per_side": 11,
        },
        "hybrid_system": {
            "global_action_constructed": False,
            "global_A_materialized": False,
            "global_F_materialized": False,
            "explicit_global_C_D_materialized": False,
            "direct_factor_count": 0,
            "external_auxiliary_rows_in_krylov": 0,
            "bottom_operator_inventory": dict(bottom.inventory),
            "top_operator_inventory": dict(top.inventory),
        },
        "validation": {
            "port_power": "not_run",
            "R_total": "not_run",
            "T_total": "not_run",
            "A_balance": "not_run",
            "A_volume_total": "not_run",
            "external_diffraction_orders": "not_run",
        },
        "physical_field_reconstruction": {"status": "not_run"},
        "official_record": False,
        "v1_r5_telemetry": {
            "task037b_v1_gate": True,
            "r5_scope": "whole-endcap ILU(0) base with fixed 40-mode Woodbury PC",
            "preconditioner_profile": R3_PRECONDITIONER_PROFILE,
            "frozen_mode_selection": selections,
            "formal_probe_count_per_side": 11,
            "sides": side_records,
            "r5_contract_pass": r5_contract_pass,
            "r5_algebra_legality_pass": r5_algebra_legality_pass,
            "r5_numerical_pass": r5_numerical_pass,
            "r5_borderline": r5_borderline,
            "severe_negative": severe_negative,
            "ordinary_default_changed": False,
            "swap": "not_evaluated_external_watchdog",
        },
        "gates": {
            "r5_record_complete": r5_contract_pass,
            "r5_all_probe_records_complete": bool(
                all(side["probe_count"] == 11 for side in side_records.values())
            ),
            "r5_all_probes_finite": bool(
                all(
                    row["finite"]
                    for side in side_records.values()
                    for row in side["rows"]
                )
            ),
            "r5_pc_linearity": bool(
                all(
                    side["pc_audit"]["linearity_error"] <= 1.0e-11
                    for side in side_records.values()
                )
            ),
            "r5_pc_determinism": bool(
                all(
                    side["pc_audit"]["determinism_error"] <= 1.0e-12
                    for side in side_records.values()
                )
            ),
            "r5_factor_noncoexistence": bool(
                bottom_released_before_top_setup
                and global_max_active_factor_count == 1
                and global_final_active_factor_count == 0
            ),
            "r5_factors_released": bool(
                all(
                    side["factor_release"]["factor_count_after"] == 0
                    and side["factor_release"]["factors_released"] is True
                    for side in side_records.values()
                )
            ),
            "r5_no_direct_fallback": bool(
                all(
                    side["no_direct_fallback"] is True for side in side_records.values()
                )
            ),
            "r5_algebra_legality_pass": r5_algebra_legality_pass,
            "r5_pass": r5_numerical_pass,
            "r5_factor_lifecycle": {
                "bottom_released_before_top_setup": bool(
                    bottom_released_before_top_setup
                ),
                "global_max_active_factor_count": int(global_max_active_factor_count),
                "global_final_active_factor_count": int(
                    global_final_active_factor_count
                ),
            },
        },
        "qualification": {
            "task037b_v1_gate": True,
            "r5_pass": r5_numerical_pass,
            "worker_numerical_pass": r5_numerical_pass,
            "integration_pass": r5_contract_pass,
            "disposition": (
                "r5_pass_awaiting_h6"
                if r5_numerical_pass
                else "DTN_WOODBURY_LOCAL_INVERSE_BORDERLINE"
                if r5_borderline
                else "WHOLE_ENDCAP_ILU0_DTN_WOODBURY_NEGATIVE"
                if r5_contract_pass
                else "DTN_WOODBURY_LOCAL_INVERSE_IMPLEMENTATION_FAILED"
            ),
            "boundary": (
                "R5 local-inverse Woodbury candidate only; R/T/A, field, and "
                "12+12 physics gates are not run."
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
            "R5 whole-endcap smoother factors and Woodbury data are sequential "
            "per side; process-tree resource review remains external watchdog "
            "evidence."
        ),
    }
    release_rhs_sets()
    raise _V1R5QualificationStop(record)


def _run_v1_r3_whole_endcap_qualification(
    *,
    args: argparse.Namespace,
    comm: MPI.Intracomm,
    provenance: dict[str, Any],
    authority_gate: dict[str, Any] | None,
    positive,
    negative,
    bottom,
    top,
    coupling,
    timings: dict[str, float],
    total_started: float,
    mark_stage,
    progress,
) -> None:
    """Run sequential whole-endcap ILU(0) R3-F/R3-A diagnostics."""

    started = time.perf_counter()
    selections = _h5_frozen_mode_selection(positive, negative)
    rhs_sets: dict[str, list[tuple[str, PETSc.Vec, dict[str, Any]]]] = {
        "bottom": [],
        "top": [],
    }
    side_records: dict[str, dict[str, Any]] = {}
    inverse = None

    def solve_summary(result) -> dict[str, Any]:
        diagnostics = result.diagnostics
        return {
            "reason": int(result.converged_reason),
            "iterations": int(result.iterations),
            "reported_residual": float(result.reported_relative_residual),
            "true_relative_residual": float(result.true_relative_residual),
            "stationary_correction_residuals": {
                str(key): float(value)
                for key, value in result.stationary_correction_residuals.items()
            },
            "setup_seconds": float(result.setup_seconds),
            "solve_seconds": float(result.solve_seconds),
            "apply_seconds": float(result.apply_seconds),
            "solution_digest": _h1_owned_vec_digest(result.solution),
            "explicit_true_residual_recomputed": bool(
                diagnostics["explicit_true_residual_recomputed"]
            ),
        }

    def diagnostics_snapshot(diagnostics: dict[str, Any]) -> dict[str, Any]:
        smoother = diagnostics["smoother"]
        lifecycle = diagnostics["lifecycle"]
        partition = diagnostics["partition_audit"]
        return {
            "operator": dict(diagnostics["operator"]),
            "configuration": dict(diagnostics["configuration"]),
            "rows": int(diagnostics["rows"]),
            "source_matrix_nnz": int(diagnostics["source_matrix_nnz"]),
            "factor_nnz": int(diagnostics["factor_nnz"]),
            "factor_csr_payload_estimate_bytes": int(
                diagnostics["factor_csr_payload_estimate_bytes"]
            ),
            "factor_csr_payload_estimate_formula": diagnostics[
                "factor_csr_payload_estimate_formula"
            ],
            "partition_audit": dict(partition),
            "owner_partition": {
                "owners": list(partition["slab_owners"]),
                "row_counts": list(partition["slab_row_counts"]),
                "intervals": list(partition["coordinate_intervals"]),
            },
            "shift": bool(smoother["subdomain_local_diagonal_shift"]),
            "factor_fingerprints": [
                dict(item) for item in smoother["factor_fingerprints"]
            ],
            "factor_count_before_destroy": int(
                lifecycle["factor_count_before_destroy"]
            ),
            "candidate_direct_factor_count": int(
                lifecycle["candidate_direct_factor_count"]
            ),
            "factor_only_storage": bool(lifecycle["factor_only_storage"]),
            "no_direct_fallback": bool(diagnostics["no_direct_fallback"]),
        }

    def result_is_finite(result: dict[str, Any]) -> bool:
        stationary = result["stationary_correction_residuals"]
        return bool(
            all(
                np.isfinite(float(result[key]))
                for key in (
                    "reported_residual",
                    "true_relative_residual",
                    "setup_seconds",
                    "solve_seconds",
                    "apply_seconds",
                )
            )
            and set(stationary) == {"1", "2", "4", "8"}
            and all(np.isfinite(float(value)) for value in stationary.values())
        )

    def run_case(
        side: str,
        case_name: str,
        operator_override: PETSc.Mat | None,
        operator_identity: str,
    ) -> dict[str, Any]:
        nonlocal inverse
        case_started = time.perf_counter()
        stage_prefix = f"v1_r3_{side}_{case_name.lower().replace('-', '_')}"
        action_system = bottom if side == "bottom" else top
        borrowed_action = (
            action_system.fine_action
            if operator_identity == "fine_action_F_only"
            else action_system.A
        )
        mark_stage(f"{stage_prefix}_setup")
        setup_started = time.perf_counter()
        inverse = build_hybrid_local_iterative_inverse(
            bottom if side == "bottom" else top,
            operator_override=operator_override,
            operator_identity=operator_identity,
            preconditioner_profile=R3_PRECONDITIONER_PROFILE,
        )
        timings[f"{stage_prefix}_setup"] = _max_elapsed(comm, setup_started)
        contract = diagnostics_snapshot(inverse._diagnostics())
        mark_stage(f"{stage_prefix}_solves")
        solve_started = time.perf_counter()
        rows: list[dict[str, Any]] = []
        try:
            for name, rhs, metadata in rhs_sets[side]:
                result = None
                try:
                    result = inverse.solve(rhs)
                    summary = solve_summary(result)
                    row = {
                        "name": name,
                        "metadata": dict(metadata),
                        "source_digest": _h1_owned_vec_digest(rhs),
                        **summary,
                        "finite": result_is_finite(summary),
                    }
                    row["pass"] = bool(
                        row["finite"]
                        and summary["reason"] > 0
                        and summary["iterations"] <= H5_MAX_IT
                        and summary["true_relative_residual"] <= 1.0e-8
                        and summary["explicit_true_residual_recomputed"]
                    )
                    progress(
                        f"Task037b V1-R3 {side}/{case_name}/{name}: "
                        f"reason={summary['reason']}, "
                        f"iterations={summary['iterations']}, "
                        f"true={summary['true_relative_residual']:.3e}"
                    )
                    rows.append(row)
                finally:
                    if result is not None:
                        result.destroy()
            timings[f"{stage_prefix}_solves"] = _max_elapsed(comm, solve_started)
        finally:
            release_started = time.perf_counter()
            released_inverse = inverse
            released_inverse.destroy()
            inverse = None
            timings[f"{stage_prefix}_release"] = _max_elapsed(comm, release_started)
            mark_stage(f"{stage_prefix}_release")
        if len(rows) != 11:
            raise RuntimeError("V1-R3 requires exactly eleven probes per side/case.")
        factor_count_after_destroy = released_inverse.factor_count_after_destroy
        factor_count_before_destroy = released_inverse.factor_count_before_destroy
        factors_released = released_inverse.factors_released
        action_survives_after_release = bool(
            borrowed_action.getType() == "python"
            and borrowed_action.getSize() == action_system.A.getSize()
        )
        contract.update(
            {
                "factor_count_before_destroy": (
                    None
                    if factor_count_before_destroy is None
                    else int(factor_count_before_destroy)
                ),
                "factor_count_after_destroy": (
                    None
                    if factor_count_after_destroy is None
                    else int(factor_count_after_destroy)
                ),
                "factors_released": bool(factors_released),
                "borrowed_action_survives_after_release": action_survives_after_release,
                "case_wall_seconds": _max_elapsed(comm, case_started),
            }
        )
        actual_operator = contract["operator"]
        return {
            "operator_identity": actual_operator["identity"],
            "external_dtn_correction": actual_operator["external_dtn_correction"],
            "preconditioner": contract,
            "probes": rows,
            "probe_count": len(rows),
            "max_true_relative_residual": max(
                row["true_relative_residual"] for row in rows
            ),
            "all_probes_finite": bool(all(row["finite"] for row in rows)),
            "pass": bool(all(row["pass"] for row in rows)),
        }

    try:
        rhs_sets["bottom"] = _h5_rhs_set(
            bottom,
            coupling.bottom,
            selections,
            side="bottom",
            propagation=coupling.propagation,
        )
        rhs_sets["top"] = _h5_rhs_set(
            top,
            coupling.top,
            selections,
            side="top",
            propagation=coupling.propagation,
        )
        for side, system in (("bottom", bottom), ("top", top)):
            side_cases = {
                "R3-F": run_case(
                    side,
                    "R3-F",
                    system.fine_action,
                    "fine_action_F_only",
                ),
                "R3-A": run_case(
                    side,
                    "R3-A",
                    None,
                    "complete_hybrid_action",
                ),
            }
            side_records[side] = {
                "cases": side_cases,
                "pass": bool(all(item["pass"] for item in side_cases.values())),
            }
        r3_pass = bool(
            all(side_record["pass"] for side_record in side_records.values())
        )
        r3_contract_pass = bool(
            len(side_records) == 2
            and all(
                len(side_record["cases"]) == 2
                and all(
                    case["probe_count"] == 11
                    and case["preconditioner"]["configuration"][
                        "preconditioner_profile"
                    ]
                    == "v1_whole_endcap_ilu0"
                    and case["preconditioner"]["configuration"]["num_slabs"] == 1
                    and case["preconditioner"]["configuration"]["overlap_fraction"]
                    == 0.0
                    and case["preconditioner"]["operator"]["identity"]
                    == case["operator_identity"]
                    and case["preconditioner"]["operator"]["external_dtn_correction"]
                    == case["external_dtn_correction"]
                    and case["preconditioner"]["no_direct_fallback"] is True
                    and case["preconditioner"]["candidate_direct_factor_count"] == 0
                    and case["preconditioner"]["factor_count_before_destroy"] == 1
                    and case["preconditioner"]["shift"] is True
                    and case["preconditioner"]["borrowed_action_survives_after_release"]
                    is True
                    and case["preconditioner"]["factors_released"] is True
                    and case["preconditioner"]["factor_count_after_destroy"] == 0
                    and np.isfinite(
                        case["preconditioner"]["partition_audit"][
                            "partition_weight_sum_error"
                        ]
                    )
                    and case["preconditioner"]["partition_audit"][
                        "partition_weight_sum_error"
                    ]
                    <= 1.0e-12
                    for case in side_record["cases"].values()
                )
                for side_record in side_records.values()
            )
        )
        timings["v1_r3_whole_endcap_qualification"] = _max_elapsed(comm, started)
        mark_stage("v1_r3_record")
        _verify_source_stable_at_end(
            comm,
            provenance,
            args.verified_clean_sha,
            args.allow_dirty_research,
        )
        record = {
            "schema_version": 1,
            "record_schema": "task037b.v1-r3-whole-endcap-ilu0.v1",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "benchmark_id": "task037b_v1_r3_whole_endcap_ilu0",
            "status": "task037b_v1_r3_complete_awaiting_r4",
            "metadata": {
                **provenance,
                "command": list(sys.argv),
                "verified_clean_sha": args.verified_clean_sha,
                "authority_gate": authority_gate,
            },
            "case": {
                "degree": args.degree,
                "h_nm": args.h_nm,
                "modal_degree": args.modal_degree,
                "modal_h_nm": args.modal_h_nm,
                "requested_modes": args.requested_modes,
                "candidate_modes": args.candidate_modes,
                "mpi_size": comm.size,
                "polarization_kind": args.polarization_kind,
                "incident_grazing_deg": args.incident_grazing_deg,
                "bottom_interface_nm": args.bottom_interface_nm,
                "top_interface_nm": args.top_interface_nm,
                "solver_path": args.solver_path,
                "operator_identity": "R3-F_then_R3-A",
                "preconditioner_profile": R3_PRECONDITIONER_PROFILE,
                "formal_rhs_count_per_side": 11,
            },
            "hybrid_system": {
                "global_action_constructed": False,
                "global_A_materialized": False,
                "global_F_materialized": False,
                "explicit_global_C_D_materialized": False,
                "direct_factor_count": 0,
                "bottom_operator_inventory": dict(bottom.inventory),
                "top_operator_inventory": dict(top.inventory),
            },
            "validation": {
                "port_power": "not_run",
                "R_total": "not_run",
                "T_total": "not_run",
                "A_balance": "not_run",
                "A_volume_total": "not_run",
            },
            "physical_field_reconstruction": {"status": "not_run"},
            "v1_r3_telemetry": {
                "task037b_v1_gate": True,
                "r3_scope": "whole-endcap ILU(0) R3-F/R3-A baseline",
                "preconditioner_profile": R3_PRECONDITIONER_PROFILE,
                "frozen_mode_selection": selections,
                "formal_probe_count_per_side": 11,
                "sides": side_records,
                "r3_contract_pass": r3_contract_pass,
                "r3_numerical_pass": r3_pass,
                "ordinary_default_changed": False,
            },
            "gates": {
                "r3_record_complete": r3_contract_pass,
                "r3_all_cases_complete": r3_contract_pass,
                "r3_all_probes_finite": bool(
                    all(
                        case["all_probes_finite"]
                        for side_record in side_records.values()
                        for case in side_record["cases"].values()
                    )
                ),
                "r3_no_direct_fallback": bool(
                    all(
                        case["preconditioner"]["candidate_direct_factor_count"] == 0
                        and case["preconditioner"]["no_direct_fallback"] is True
                        for side_record in side_records.values()
                        for case in side_record["cases"].values()
                    )
                ),
                "r3_factors_released": r3_contract_pass,
                "r3_pass": r3_pass,
            },
            "qualification": {
                "task037b_v1_gate": True,
                "r3_pass": r3_pass,
                "worker_numerical_pass": r3_pass,
                "integration_pass": r3_contract_pass,
                "disposition": (
                    "r3_numerical_pass_awaiting_r4"
                    if r3_pass
                    else "r3_numerical_negative_awaiting_r4"
                ),
                "boundary": (
                    "R3-F/R3-A whole-endcap ILU(0) baseline only; R4/R5 and "
                    "R/T/A/field/12+12 physics gates are not run."
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
                "R3-F and R3-A are sequential whole-endcap factors; resource "
                "samples remain external watchdog evidence."
            ),
        }
        raise _V1R3QualificationStop(record)
    finally:
        if inverse is not None:
            inverse.destroy()
        for rhs_list in rhs_sets.values():
            for _name, vector, _metadata in rhs_list:
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
        or args.task037b_v1_gate
        or args.task037b_v2_gate
        or args.task037b_v3_gate
        or args.task037b_v4_gate
    ) and comm.size not in TASK035C_P6_H10_MPI_SIZES:
        raise SystemExit("Task035c p6/h10 Hybrid is restricted to MPI1/2/4/8.")
    if (
        args.task037b_h1_gate
        or args.task037b_h3_gate
        or args.task037b_h4_gate
        or args.task037b_h5_gate
        or args.task037b_v1_gate
        or args.task037b_v2_gate
        or args.task037b_v3_gate
        or args.task037b_v4_gate
    ) and comm.size != 8:
        raise SystemExit(
            "Task037b H1/H3/H4/H5/V1/V2/V3/V4 Hybrid is restricted to MPI8."
        )
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

        if args.task037b_v2_gate or args.task037b_v3_gate or args.task037b_v4_gate:
            mark_stage(
                "action_coupling_build_started"
                if args.task037b_v3_gate or args.task037b_v4_gate
                else "v2_action_coupling_build"
            )
            started = time.perf_counter()
            bottom = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
                log=progress,
            )
            top = assemble_hybrid_local_dtn_action_system(
                cfg,
                "top",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
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
            coupling_key = (
                "action_coupling_build"
                if args.task037b_v3_gate
                else "v4_action_coupling_build"
                if args.task037b_v4_gate
                else "v2_action_coupling_build"
            )
            timings[coupling_key] = _max_elapsed(comm, started)
            if args.task037b_v3_gate or args.task037b_v4_gate:
                mark_stage("action_coupling_build_ready")
            if args.task037b_v4_gate:
                _run_v4_full_solve(
                    args=args,
                    comm=comm,
                    provenance=provenance,
                    authority_gate=task035c_p6_gate,
                    cfg=cfg,
                    cross_section=cross_section,
                    positive=positive,
                    negative=negative,
                    bottom=bottom,
                    top=top,
                    coupling=coupling,
                    timings=timings,
                    total_started=total_started,
                    mark_stage=mark_stage,
                    v5_multimetric=args.task037b_v5_gate,
                    v6_traction_aligned=args.task037b_v6_gate,
                )
            else:
                _run_v2_block_screen(
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
                    timings=timings,
                    total_started=total_started,
                    mark_stage=mark_stage,
                    progress=progress,
                )
        elif args.task037b_h3_gate or args.task037b_h4_gate or args.task037b_h5_gate:
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
                timings["h5_action_coupling_build"] = _max_elapsed(comm, started)
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
                        "frobenius_norm": h4a_modal_diagnostic[
                            "feedback_frobenius_norm"
                        ],
                        "relative_to_s_m": h4a_modal_diagnostic[
                            "feedback_relative_to_s_m"
                        ],
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
                        np.linalg.norm(h3_direct_comparison_solution.modal_amplitudes)
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
        elif args.task037b_v1_gate:
            mark_stage("v1_action_coupling_build")
            started = time.perf_counter()
            bottom = assemble_hybrid_local_dtn_action_system(
                cfg,
                "bottom",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
                log=progress,
            )
            top = assemble_hybrid_local_dtn_action_system(
                cfg,
                "top",
                bottom_interface_z_nm=args.bottom_interface_nm,
                top_interface_z_nm=args.top_interface_nm,
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
            timings["v1_action_coupling_build"] = _max_elapsed(comm, started)
            if args.solver_path == "dtn-woodbury-oracle-qualification":
                _run_v1_r4_woodbury_qualification(
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
                    timings=timings,
                    total_started=total_started,
                    mark_stage=mark_stage,
                    progress=progress,
                )
            elif args.solver_path == "dtn-woodbury-local-inverse-qualification":
                _run_v1_r5_local_inverse_qualification(
                    args=args,
                    comm=comm,
                    provenance=provenance,
                    authority_gate=task035c_p6_gate,
                    positive=positive,
                    negative=negative,
                    bottom=bottom,
                    top=top,
                    coupling=coupling,
                    timings=timings,
                    total_started=total_started,
                    mark_stage=mark_stage,
                    progress=progress,
                )
            elif args.solver_path == "whole-endcap-ilu0-qualification":
                _run_v1_r3_whole_endcap_qualification(
                    args=args,
                    comm=comm,
                    provenance=provenance,
                    authority_gate=task035c_p6_gate,
                    positive=positive,
                    negative=negative,
                    bottom=bottom,
                    top=top,
                    coupling=coupling,
                    timings=timings,
                    total_started=total_started,
                    mark_stage=mark_stage,
                    progress=progress,
                )
            elif args.solver_path == "f-only-local-inverse-qualification":
                _run_v1_r2_f_only_qualification(
                    args=args,
                    comm=comm,
                    provenance=provenance,
                    authority_gate=task035c_p6_gate,
                    positive=positive,
                    negative=negative,
                    bottom=bottom,
                    top=top,
                    coupling=coupling,
                    timings=timings,
                    total_started=total_started,
                    mark_stage=mark_stage,
                    progress=progress,
                )
            else:
                _run_v1_dtn_component_qualification(
                    args=args,
                    comm=comm,
                    provenance=provenance,
                    authority_gate=task035c_p6_gate,
                    positive=positive,
                    negative=negative,
                    bottom=bottom,
                    top=top,
                    coupling=coupling,
                    timings=timings,
                    total_started=total_started,
                    mark_stage=mark_stage,
                    progress=progress,
                )
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
                    "h4b_diagnostic_finite": bool(h4b_finite and h4_diagnostic_finite),
                    "h4b_evidence_complete": bool(
                        h4_telemetry is not None
                        and h4b_before_inventory is not None
                        and h4b_after_inventory is not None
                    ),
                    "h4b_factors_released": bool(
                        h4b_after_inventory is not None
                        and h4b_before_inventory is not None
                        and h4b_before_inventory["oracle_local_direct_factor_count"]
                        == 2
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
            if args.task037b_h1_authority_export:
                authority_run_dir = Path(args.output).parent
                authority_npz = authority_run_dir / "h1_authority_grid_EH_modal_q.npz"
                auxiliary = validation["external_auxiliary_amplitudes"]
                if comm.rank == 0:
                    authority_grid = _write_authority_grid_payload(
                        authority_npz,
                        sample_x=sample_x,
                        sample_y=sample_y,
                        sample_z=sample_z,
                        electric=selected_planes.electric_V_per_m,
                        magnetic=selected_planes.magnetic_A_per_m,
                        modal=solution.modal_amplitudes,
                        bottom_q=auxiliary["bottom"],
                        top_q=auxiliary["top"],
                        schema="task037b.h1-authority-grid-EH-modal-q.v1",
                    )
                else:
                    authority_grid = None
                authority_grid = comm.bcast(authority_grid, root=0)
                authority_canonical = _write_canonical_manifest_exports(
                    systems={"bottom": bottom, "top": top},
                    physical_solution=solution,
                    run_dir=authority_run_dir,
                    comm=comm,
                    prefix="task037b_h1",
                )
                authority_payload_complete = bool(
                    all(
                        authority_canonical.get(side, {})
                        .get("roles", {})
                        .get(role, {})
                        .get("pass")
                        is True
                        for side in ("bottom", "top")
                        for role in ("active_trace", "full_fe")
                    )
                )
                if not authority_payload_complete:
                    raise RuntimeError("H1 authority canonical payload is incomplete.")
                h1_telemetry.update(
                    {
                        "own_grid": authority_grid,
                        "canonical_export": authority_canonical,
                        "authority_payload": {
                            "numeric_npz": authority_grid,
                            "canonical_export": authority_canonical,
                            "payload_complete": authority_payload_complete,
                        },
                    }
                )
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
            h4_telemetry["post_h4_direct_factor_inventory"] = h3_direct_factor_inventory
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
                    if (args.task037b_h3_gate or args.task037b_h4_gate)
                    and system is not None
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
                    "runner_gate_pass_12_channel_pending"
                    if integration_pass
                    else "HYBRID_BLOCK_ITERATIVE_ALGEBRA_FAILED"
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
    except _V4QualificationStop as stop:
        record = stop.record
    except _V3QualificationStop as stop:
        record = stop.record
    except _V2QualificationStop as stop:
        record = stop.record
    except _V1R4QualificationStop as stop:
        record = stop.record
    except _V1R5QualificationStop as stop:
        record = stop.record
    except _V1R3QualificationStop as stop:
        record = stop.record
    except _V1R2QualificationStop as stop:
        record = stop.record
    except _V1QualificationStop as stop:
        record = stop.record
    except _H5QualificationStop as stop:
        record = stop.record
        h3_oracle_bottom = None
        h3_oracle_top = None
    except _ModalBasisCapacityStop:
        pass
    finally:
        if args.task037b_v4_gate:
            mark_stage("v4_postprocess_release_started")
            v4_release_started = time.perf_counter()
            v4_postprocess_release: dict[str, Any] = {
                "release_order": [],
                "objects": {},
            }
            if system is not None:
                system.destroy()
                v4_postprocess_release["release_order"].append("action_system")
                v4_postprocess_release["objects"]["action_system"] = {
                    "destroy_call_completed": True,
                    "destroyed": bool(getattr(system, "_destroyed", False)),
                }
                system = None
            for side, local_system in (("bottom", bottom), ("top", top)):
                if local_system is not None:
                    local_system.destroy()
                    v4_postprocess_release["release_order"].append(
                        f"{side}_static_condensation_cache"
                    )
                    v4_postprocess_release["objects"][
                        f"{side}_static_condensation_cache"
                    ] = {
                        "destroy_call_completed": True,
                        "destroyed": bool(getattr(local_system, "_destroyed", False)),
                    }
            bottom = None
            top = None
            if coupling is not None:
                coupling.destroy()
                v4_postprocess_release["release_order"].append("coupling")
                v4_postprocess_release["objects"]["coupling"] = {
                    "destroy_call_completed": True,
                    "destroy_state": "not_exposed",
                }
                coupling = None
            for name, basis in (
                ("positive_modal_basis", positive),
                ("negative_modal_basis", negative),
            ):
                if basis is not None:
                    basis.destroy()
                    v4_postprocess_release["release_order"].append(name)
                    v4_postprocess_release["objects"][name] = {
                        "destroy_call_completed": True,
                        "destroy_state": "not_exposed",
                    }
            positive = None
            negative = None
            if operators is not None:
                operators.destroy()
                v4_postprocess_release["release_order"].append("qep_operators")
                v4_postprocess_release["objects"]["qep_operators"] = {
                    "destroy_call_completed": True,
                    "destroy_state": "not_exposed",
                }
                operators = None
            v4_postprocess_release["release_seconds"] = _max_elapsed(
                comm, v4_release_started
            )
            expected_release_objects = {
                "bottom_static_condensation_cache",
                "top_static_condensation_cache",
                "coupling",
                "positive_modal_basis",
                "negative_modal_basis",
                "qep_operators",
            }
            if "action_system" in v4_postprocess_release["objects"]:
                expected_release_objects.add("action_system")
            v4_postprocess_release["release_pass"] = bool(
                set(v4_postprocess_release["objects"]) == expected_release_objects
                and all(
                    item.get("destroy_call_completed") is True
                    for item in v4_postprocess_release["objects"].values()
                )
            )
            if record is not None:
                v4_telemetry = record.setdefault("v4_telemetry", {})
                v4_markers = v4_telemetry.setdefault("stage_markers", [])
                v4_markers.append("v4_postprocess_release_started")
                v4_telemetry["main_postprocess_release"] = v4_postprocess_release
                v4_timing = record.setdefault("timing_seconds_max_rank", {})
                v4_timing["v4_postprocess_release"] = v4_postprocess_release[
                    "release_seconds"
                ]
                v4_timing["total"] = _max_elapsed(comm, total_started)
            mark_stage("v4_postprocess_release_finished")
            if record is not None:
                record["v4_telemetry"]["stage_markers"].append(
                    "v4_postprocess_release_finished"
                )
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

    if args.task037b_v4_gate:
        mark_stage("v4_worker_cleanup_finished")
        if record is not None:
            record["v4_telemetry"]["stage_markers"].append("v4_worker_cleanup_finished")
            record["timing_seconds_max_rank"]["total"] = _max_elapsed(
                comm, total_started
            )
            postprocess_release = record["v4_telemetry"].get(
                "main_postprocess_release", {}
            )
            postprocess_release_pass = bool(
                postprocess_release.get("release_pass") is True
            )
            record["qualification"]["postprocess_release_pass"] = (
                postprocess_release_pass
            )
            final_integration_pass = bool(
                record["qualification"].get("integration_pass") is True
                and postprocess_release_pass
            )
            record["qualification"]["integration_pass"] = final_integration_pass
            record["v4_telemetry"]["final_integration_pass"] = final_integration_pass
            if not postprocess_release_pass:
                record["status"] = "task037b_v4_postprocess_release_failed"
                record["qualification"]["disposition"] = (
                    "DOUBLE_APPROXIMATE_IMPLEMENTATION_GATE_FAILED"
                )

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
