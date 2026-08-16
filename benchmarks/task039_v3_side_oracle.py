"""Research-only V3-7 side-oracle and direct-solution wiring helpers.

The module deliberately owns no runner lifecycle and never creates a global
Hybrid direct factor.  It consumes one already-built MPI setup and returns
small, JSON-ready diagnostics; the caller owns the setup and raw artifacts.
"""

from __future__ import annotations

from pathlib import Path
from collections.abc import Callable, Mapping
from types import SimpleNamespace
from typing import Any

import numpy as np
from petsc4py import PETSc

from benchmarks.canonical_vector_artifacts import read_canonical_packet_shard
from src.solvers.hcurl_canonical_vector_dolfinx import (
    reconstruct_canonical_full_fe_function,
)
from src.solvers.hybrid_fem_modal_block_ldu import (
    HybridBlockLduIterativeConfig,
    create_research_exact_side_lu_block_ldu_preconditioner,
    solve_hybrid_block_ldu_iterative,
)
from src.solvers.hybrid_fem_modal_iterative import create_hybrid_assembled_block_action
from src.solvers.hybrid_local_dtn_woodbury import create_research_exact_side_lu_action
from src.solvers.condensed_dtn import (
    condensed_rhs,
    create_matrix_free_condensed_operator,
    materialize_research_explicit_dtn_blocks,
)
from src.solvers.static_local_schur_action import (
    materialize_research_explicit_fine_matrix,
)


def select_current_full_fe_shard(
    inventory: Mapping[str, Any], side: str, rank: int
) -> dict[str, Any]:
    """Return the verified full-FE shard owned by ``rank`` for one side."""

    if side not in {"bottom", "top"}:
        raise ValueError("side must be bottom or top")
    canonical = inventory.get("canonical")
    entry = canonical.get(f"{side}.full_fe") if isinstance(canonical, Mapping) else None
    if not isinstance(entry, Mapping):
        raise ValueError(f"missing verified {side}.full_fe inventory")
    manifest = entry.get("manifest")
    shards = entry.get("shards")
    if not isinstance(manifest, Mapping) or not isinstance(shards, list):
        raise ValueError(f"{side}.full_fe shard inventory is incomplete")
    manifest_path = Path(str(manifest["path"])).resolve()
    matches = [item for item in shards if item.get("rank") == int(rank)]
    if len(matches) != 1:
        raise ValueError(f"{side}.full_fe has no unique shard for rank {rank}")
    shard = matches[0]
    filename = shard.get("filename")
    digest = shard.get("file_sha256")
    if not isinstance(filename, str) or Path(filename).is_absolute():
        raise ValueError("canonical shard filename is not relative")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("canonical shard SHA is invalid")
    path = (manifest_path.parent / filename).resolve()
    return {
        "side": side,
        "rank": int(rank),
        "manifest_path": str(manifest_path),
        "path": str(path),
        "sha256": digest,
        "packet_count": int(shard.get("packet_count", -1)),
    }


def rebuild_hybrid_augmented_vector(
    inventory: Mapping[str, Any],
    bottom_system: Any,
    top_system: Any,
    layout: Any,
    modal_amplitudes: np.ndarray,
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Rebuild a current-layout ``x*`` from verified full-FE packets.

    Each rank reads only its own full-FE shard.  The fresh fields are reduced
    through the current condensed trace ownership map; modal amplitudes are
    inserted through the current ``HybridAugmentedLayout``.  This V3 action
    layout deliberately has no auxiliary rows.
    """

    comm = layout.comm
    active: dict[str, np.ndarray] = {}
    mapping_audit: dict[str, Any] = {}
    for side, system in (("bottom", bottom_system), ("top", top_system)):
        static = getattr(system, "static_condensation", None)
        condensed = getattr(static, "condensed", None)
        if condensed is None:
            raise ValueError(f"{side} system has no condensed trace ownership map")
        selected = select_current_full_fe_shard(inventory, side, comm.rank)
        packets = read_canonical_packet_shard(
            Path(selected["path"]), selected["sha256"]
        )
        declared_packet_count = int(selected["packet_count"])
        actual_packet_count = len(packets)
        if actual_packet_count != declared_packet_count:
            raise ValueError(
                f"{side} shard packet count mismatch: "
                f"declared={declared_packet_count}, actual={actual_packet_count}"
            )
        field = reconstruct_canonical_full_fe_function(
            system.V,
            packets,
            system.floquet_data,
        )
        index_map = field.function_space.dofmap.index_map
        block_size = int(field.function_space.dofmap.index_map_bs)
        owned_blocks = np.arange(int(index_map.size_local), dtype=np.int32)
        global_blocks = np.asarray(
            index_map.local_to_global(owned_blocks), dtype=np.int64
        )
        components = np.arange(block_size, dtype=np.int64)
        global_dofs = (global_blocks[:, None] * block_size + components).reshape(-1)
        if len(global_dofs) != actual_packet_count:
            raise ValueError(
                f"{side} full-FE row/packet mismatch: "
                f"owned_full_fe_rows={len(global_dofs)}, "
                f"actual_packets={actual_packet_count}"
            )
        values = np.asarray(field.x.array[: len(global_dofs)], dtype=np.complex128)
        if values.shape != global_dofs.shape or not np.isfinite(values).all():
            raise ValueError(f"{side} reconstructed field is not finite")
        lookup = {
            int(global_id): value for global_id, value in zip(global_dofs, values)
        }
        active_original = np.asarray(
            condensed.trace_constraints.owned_active_original_dofs, dtype=np.int64
        )
        try:
            active[side] = np.asarray(
                [lookup[int(global_id)] for global_id in active_original],
                dtype=np.complex128,
            )
        except KeyError as exc:
            raise ValueError(
                f"{side} active trace ownership is absent from fresh field"
            ) from exc
        if not np.isfinite(active[side]).all():
            raise ValueError(f"{side} active trace values are not finite")
        mapping_audit[side] = {
            "shard_path": selected["path"],
            "sha256": selected["sha256"],
            "declared_packet_count": declared_packet_count,
            "actual_packet_count": actual_packet_count,
            "owned_full_fe_rows": int(len(global_dofs)),
            "owned_active_rows": int(len(active[side])),
        }
        del field

    vectors: dict[str, PETSc.Vec] = {}
    try:
        for side, system in (("bottom", bottom_system), ("top", top_system)):
            vector = system.A.createVecRight()
            vectors[side] = vector
            local = vector.getArray()
            owned_active_rows = int(
                getattr(system.static_condensation.condensed, "owned_active_rows")
            )
            if (
                vector.getLocalSize() != owned_active_rows
                or len(active[side]) != owned_active_rows
            ):
                raise ValueError(
                    f"{side} action vector does not match active ownership"
                )
            local[:] = active[side]
            vector.assemble()
        modal = np.asarray(modal_amplitudes, dtype=np.complex128)
        if modal.shape != (layout.modal_count,) or not np.isfinite(modal).all():
            raise ValueError("modal amplitude payload does not match current layout")
        result = layout.pack(vectors["bottom"], vectors["top"], modal)
    finally:
        for vector in vectors.values():
            vector.destroy()
    return result, {
        "mapping_status": "canonical_full_fe_to_owned_active_trace",
        "rank": int(comm.rank),
        "bottom_active_rows": int(len(active["bottom"])),
        "top_active_rows": int(len(active["top"])),
        "modal_count": int(layout.modal_count),
        "auxiliary_status": "not_in_layout_action_only",
        "mapping_audit": mapping_audit,
    }


def _block_norm(values: np.ndarray, block_slice: slice, comm: Any) -> float:
    local = float(np.vdot(values[block_slice], values[block_slice]).real)
    return float(np.sqrt(comm.allreduce(local)))


def _audit_one_operator_vector(
    assembled_matrix: PETSc.Mat,
    matrix_free_matrix: PETSc.Mat,
    layout: Any,
    source: PETSc.Vec,
    relative_limit: float,
) -> dict[str, Any]:
    if source.getSize() != assembled_matrix.getSize()[1]:
        raise ValueError("identity vector has the wrong size")
    assembled = assembled_matrix.createVecLeft()
    matrix_free = matrix_free_matrix.createVecLeft()
    difference = assembled.duplicate()
    try:
        assembled_matrix.mult(source, assembled)
        matrix_free_matrix.mult(source, matrix_free)
        difference.waxpy(PETSc.ScalarType(-1.0), matrix_free, assembled)
        assembled_values = np.asarray(assembled.getArray(readonly=True))
        difference_values = np.asarray(difference.getArray(readonly=True))
        overall_denominator = max(float(assembled.norm()), 1.0e-30)
        overall_relative = float(difference.norm()) / overall_denominator
        blocks: dict[str, Any] = {}
        for block, block_slice in (
            ("bottom", layout.local_bottom_slice),
            ("top", layout.local_top_slice),
            ("modal", layout.local_modal_slice),
        ):
            numerator = _block_norm(difference_values, block_slice, layout.comm)
            denominator = max(
                _block_norm(assembled_values, block_slice, layout.comm),
                1.0e-30,
            )
            relative = numerator / denominator
            blocks[block] = {
                "relative_error": float(relative),
                "reference_norm": float(denominator),
                "limit": float(relative_limit),
                "pass": bool(np.isfinite(relative) and relative <= relative_limit),
            }
        output_norms = {
            block: _block_norm(assembled_values, block_slice, layout.comm)
            for block, block_slice in (
                ("bottom", layout.local_bottom_slice),
                ("top", layout.local_top_slice),
                ("modal", layout.local_modal_slice),
            )
        }
        return {
            "relative_error": float(overall_relative),
            "denominator": "max(norm(assembled_action),1e-30)",
            "limit": float(relative_limit),
            "pass": bool(
                np.isfinite(overall_relative)
                and overall_relative <= relative_limit
                and all(item["pass"] for item in blocks.values())
            ),
            "blocks": blocks,
            "assembled_output_norms": output_norms,
        }
    finally:
        difference.destroy()
        matrix_free.destroy()
        assembled.destroy()


def _relative_vec_difference(left: PETSc.Vec, right: PETSc.Vec) -> float:
    if left.getSize() != right.getSize():
        raise ValueError("RHS vectors have different global sizes")
    difference = left.duplicate()
    try:
        difference.waxpy(PETSc.ScalarType(-1.0), right, left)
        return float(difference.norm()) / max(float(left.norm()), 1.0e-30)
    finally:
        difference.destroy()


def audit_hybrid_operator_identity(
    assembled_matrix: PETSc.Mat,
    matrix_free_matrix: PETSc.Mat,
    layout: Any,
    vectors: Mapping[str, PETSc.Vec],
    *,
    rhs_pairs: Mapping[str, tuple[PETSc.Vec, PETSc.Vec]] | None = None,
    isolated_vectors: Mapping[str, PETSc.Vec] | None = None,
    relative_limit: float = 1.0e-10,
) -> dict[str, Any]:
    """Audit assembled/action equality and isolated bottom/top/modal inputs.

    ``isolated_vectors`` is expected to contain ``bottom_only``, ``top_only``
    and ``modal_only``.  These are separate inputs for the P/T coupling audit,
    not labels attached to one physical RHS.  ``rhs_pairs`` compares an
    independently assembled RHS against its matrix-free counterpart.
    """

    if not vectors:
        raise ValueError("operator identity audit needs at least one vector")
    if assembled_matrix.getSize() != matrix_free_matrix.getSize():
        raise ValueError("assembled and matrix-free matrices have different sizes")
    reports = {
        str(label): _audit_one_operator_vector(
            assembled_matrix,
            matrix_free_matrix,
            layout,
            source,
            relative_limit,
        )
        for label, source in vectors.items()
    }
    if isolated_vectors is None:
        isolation = {
            "status": "not_provided",
            "pass": False,
            "vectors": {},
        }
    else:
        required = {"bottom_only", "top_only", "modal_only"}
        if set(isolated_vectors) != required:
            raise ValueError(
                "isolated_vectors must contain bottom/top/modal-only inputs"
            )
        isolation_vectors = {
            label: _audit_one_operator_vector(
                assembled_matrix,
                matrix_free_matrix,
                layout,
                source,
                relative_limit,
            )
            for label, source in isolated_vectors.items()
        }
        source_support: dict[str, Any] = {}
        for label, source in isolated_vectors.items():
            values = np.asarray(source.getArray(readonly=True))
            norms = {
                block: _block_norm(values, block_slice, layout.comm)
                for block, block_slice in (
                    ("bottom", layout.local_bottom_slice),
                    ("top", layout.local_top_slice),
                    ("modal", layout.local_modal_slice),
                )
            }
            unexpected = sum(
                value
                for block, value in norms.items()
                if block != label.removesuffix("_only")
            )
            source_support[label] = {
                "block_norms": norms,
                "unexpected_source_norm": float(unexpected),
                "pass": bool(
                    np.isfinite(unexpected)
                    and unexpected <= 1.0e-30
                    and norms[label.removesuffix("_only")] > 0.0
                ),
                "expected_input_block": label.removesuffix("_only"),
            }
        metrics = {
            "P_bottom": dict(isolation_vectors["bottom_only"]["blocks"]["modal"]),
            "P_top": dict(isolation_vectors["top_only"]["blocks"]["modal"]),
            "T_bottom": dict(isolation_vectors["modal_only"]["blocks"]["bottom"]),
            "T_top": dict(isolation_vectors["modal_only"]["blocks"]["top"]),
        }
        isolation = {
            "status": "isolated_side_modal_inputs",
            "pass": bool(
                all(item["pass"] for item in isolation_vectors.values())
                and all(item["pass"] for item in source_support.values())
            ),
            "vectors": isolation_vectors,
            "source_support": source_support,
            "P_bottom": metrics["P_bottom"],
            "P_top": metrics["P_top"],
            "T_bottom": metrics["T_bottom"],
            "T_top": metrics["T_top"],
        }
    rhs_reports = {}
    if rhs_pairs is not None:
        rhs_reports = {
            str(label): {
                "relative_error": float(_relative_vec_difference(left, right)),
                "limit": float(relative_limit),
            }
            for label, (left, right) in rhs_pairs.items()
        }
        for report in rhs_reports.values():
            report["pass"] = bool(
                np.isfinite(report["relative_error"])
                and report["relative_error"] <= relative_limit
            )
    rhs_pass = bool(rhs_reports) and all(item["pass"] for item in rhs_reports.values())
    vector_pass = all(item["pass"] for item in reports.values())
    return {
        "vector_count": len(reports),
        "vectors": reports,
        "rhs_equality": {
            "status": "provided" if rhs_pairs is not None else "not_provided",
            "pass": rhs_pass,
            "vectors": rhs_reports,
        },
        "coupling_isolation": isolation,
        "pass": bool(vector_pass and rhs_pass and isolation["pass"]),
    }


def _audit_explicit_f_action(
    explicit_f: PETSc.Mat,
    fine_action: PETSc.Mat,
    *,
    relative_limit: float = 1.0e-12,
) -> dict[str, Any]:
    if explicit_f.getSize() != fine_action.getSize():
        raise ValueError("explicit F and fine action have different sizes")
    maximum = 0.0
    source = fine_action.createVecRight()
    explicit = explicit_f.createVecLeft()
    fine = fine_action.createVecLeft()
    difference = fine.duplicate()
    try:
        first, last = (int(value) for value in source.getOwnershipRange())
        for seed in (739, 743):
            rng = np.random.default_rng(seed)
            source.getArray()[:] = np.asarray(
                rng.standard_normal(last - first)
                + 1j * rng.standard_normal(last - first),
                dtype=PETSc.ScalarType,
            )
            explicit_f.mult(source, explicit)
            fine_action.mult(source, fine)
            difference.waxpy(PETSc.ScalarType(-1.0), fine, explicit)
            relative = float(difference.norm()) / max(float(fine.norm()), 1.0e-30)
            maximum = max(maximum, relative)
    finally:
        difference.destroy()
        fine.destroy()
        explicit.destroy()
        source.destroy()
    return {
        "relative_error": float(maximum),
        "limit": float(relative_limit),
        "pass": bool(np.isfinite(maximum) and maximum <= relative_limit),
        "denominator": "max(norm(fine_action*x),1e-30)",
    }


class _ResearchEliminatedSide:
    """Own one explicit-component eliminated side reference."""

    def __init__(
        self,
        *,
        F: PETSc.Mat,
        C: PETSc.Mat,
        D: PETSc.Mat,
        H: PETSc.Mat,
        b: PETSc.Vec,
        A: PETSc.Mat,
        A_context: Any,
        source_system: Any,
        dtn_audit: Mapping[str, Any],
    ) -> None:
        self.F = F
        self.C = C
        self.D = D
        self.H = H
        self.b = b
        self.A = A
        self.A_context = A_context
        self.local_mesh = source_system.local_mesh
        self.global_size = int(A.getSize()[0])
        self.n_fe = self.global_size
        self.n_external_aux = 0
        self.external_modes = list(source_system.external_modes)
        self.inventory = {
            "matrix_type": "python",
            "matrix_free": True,
            "global_A_materialized": False,
            "global_F_materialized": True,
            "explicit_external_c_matrix_count": 1,
            "explicit_external_d_matrix_count": 1,
            "direct_factor_count": 0,
            "research_explicit_dtn": dict(dtn_audit),
        }
        self._destroyed = False

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.A_context.destroy()
        self.A.destroy()
        self.b.destroy()
        self.H.destroy()
        self.D.destroy()
        self.C.destroy()
        self.F.destroy()
        self._destroyed = True


class ResearchHybridReference:
    """Thin independent Hybrid reference built from explicit side components."""

    def __init__(
        self,
        bottom: _ResearchEliminatedSide,
        top: _ResearchEliminatedSide,
        operator: PETSc.Mat,
        operator_context: Any,
    ) -> None:
        self.bottom = bottom
        self.top = top
        self.operator = operator
        self.operator_context = operator_context
        self._destroyed = False

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.operator_context.destroy()
        self.operator.destroy()
        self.top.destroy()
        self.bottom.destroy()
        self._destroyed = True


def _build_research_eliminated_side(system: Any) -> _ResearchEliminatedSide:
    fine = None
    dtn = None
    action = None
    action_context = None
    rhs = None
    try:
        fine = materialize_research_explicit_fine_matrix(
            system.static_condensation.condensed
        )
        dtn = materialize_research_explicit_dtn_blocks(system.blocks)
        blocks = SimpleNamespace(
            F=fine,
            C=dtn.C,
            D=dtn.D,
            H=dtn.H,
            n_fe=int(fine.getSize()[0]),
            n_aux=int(dtn.H.getSize()[0]),
            require_f=lambda: fine,
        )
        action, action_context = create_matrix_free_condensed_operator(
            blocks,
            fine_operator=fine,
        )
        rhs = condensed_rhs(
            SimpleNamespace(
                b_fe=system.blocks.b_fe,
                b_aux=system.blocks.b_aux,
                C=dtn.C,
                D=dtn.D,
                H=dtn.H,
            )
        )
        side = _ResearchEliminatedSide(
            F=fine,
            C=dtn.C,
            D=dtn.D,
            H=dtn.H,
            b=rhs,
            A=action,
            A_context=action_context,
            source_system=system,
            dtn_audit=dtn.audit,
        )
        fine = None
        dtn = None
        action = None
        action_context = None
        rhs = None
        return side
    except Exception:
        if action_context is not None:
            action_context.destroy()
        if action is not None:
            action.destroy()
        if rhs is not None:
            rhs.destroy()
        if dtn is not None:
            dtn.destroy()
        if fine is not None:
            fine.destroy()
        raise


def build_research_independent_hybrid_reference(
    bottom_system: Any,
    top_system: Any,
    coupling: Any,
) -> ResearchHybridReference:
    """Build explicit-component eliminated actions without a dense global matrix."""

    bottom = None
    top = None
    operator = None
    operator_context = None
    try:
        bottom = _build_research_eliminated_side(bottom_system)
        top = _build_research_eliminated_side(top_system)
        operator, operator_context = create_hybrid_assembled_block_action(
            bottom,
            top,
            coupling,
        )
        reference = ResearchHybridReference(bottom, top, operator, operator_context)
        bottom = None
        top = None
        operator = None
        operator_context = None
        return reference
    except Exception:
        if operator_context is not None:
            operator_context.destroy()
        if operator is not None:
            operator.destroy()
        if top is not None:
            top.destroy()
        if bottom is not None:
            bottom.destroy()
        raise


def run_exact_side_lu_oracle(
    layout: Any,
    bottom_system: Any,
    top_system: Any,
    coupling: Any,
    rhs: PETSc.Vec,
    *,
    factor_solver_type: str | None = "mumps",
    max_it: int = 100,
    restart: int = 90,
    threshold: float = 5.0e-9,
    matrix_repeat_tolerance: float = 1.0e-13,
    solution_consumer: Callable[[PETSc.Vec, Mapping[str, Any]], Any] | None = None,
    reference: Any | None = None,
) -> dict[str, Any]:
    """Run one exact-side oracle and consume the solution before cleanup."""

    bottom_components = None
    top_components = None
    bottom_action = None
    top_action = None
    operator = None
    operator_context = None
    context = None
    result = None
    report = None
    reference_destroyed = False
    reference_owned = reference is None
    try:
        if reference is None:
            reference = build_research_independent_hybrid_reference(
                bottom_system,
                top_system,
                coupling,
            )
        bottom_reference = reference.bottom
        top_reference = reference.top
        bottom_explicit = bottom_reference.F
        top_explicit = top_reference.F
        bottom_components = SimpleNamespace(
            F=bottom_explicit,
            C=bottom_reference.C,
            D=bottom_reference.D,
            H=bottom_reference.H,
        )
        top_components = SimpleNamespace(
            F=top_explicit,
            C=top_reference.C,
            D=top_reference.D,
            H=top_reference.H,
        )
        for side, system, components in (
            ("bottom", bottom_system, bottom_components),
            ("top", top_system, top_components),
        ):
            expected_modes = len(system.external_modes)
            if components.H.getSize() != (expected_modes, expected_modes):
                raise ValueError(f"{side} dynamic mode count does not match H")
        explicit_audit = {
            "bottom": _audit_explicit_f_action(
                bottom_explicit, bottom_system.fine_action
            ),
            "top": _audit_explicit_f_action(top_explicit, top_system.fine_action),
        }
        if not all(item["pass"] for item in explicit_audit.values()):
            raise ValueError("research explicit F does not match fine action")
        bottom_action = create_research_exact_side_lu_action(
            bottom_explicit,
            bottom_components,
            factor_solver_type=factor_solver_type,
        )
        top_action = create_research_exact_side_lu_action(
            top_explicit,
            top_components,
            factor_solver_type=factor_solver_type,
        )
        operator, operator_context = create_hybrid_assembled_block_action(
            bottom_system,
            top_system,
            coupling,
        )
        context = create_research_exact_side_lu_block_ldu_preconditioner(
            layout,
            bottom_system,
            top_system,
            coupling,
            bottom_action,
            top_action,
            matrix_repeat_tolerance=matrix_repeat_tolerance,
        )
        result = solve_hybrid_block_ldu_iterative(
            operator,
            rhs,
            context,
            config=HybridBlockLduIterativeConfig(
                restart=restart,
                max_it=max_it,
                threshold=threshold,
                initial_guess="zero",
            ),
        )
        inventory = dict(context.inventory)
        residuals = {
            key: float(result.postsolve_audit[key])
            for key in (
                "reported_relative_residual",
                "global_true_relative_residual",
                "bottom_true_relative_residual",
                "top_true_relative_residual",
                "modal_true_relative_residual",
            )
        }
        numerical_pass = bool(
            int(result.converged_reason) > 0
            and 0 < int(result.iterations) <= int(max_it)
            and all(
                np.isfinite(value) and value <= float(threshold)
                for value in residuals.values()
            )
        )
        inventory_pass = bool(
            inventory.get("bottom_direct_factor_count") == 1
            and inventory.get("top_direct_factor_count") == 1
            and inventory.get("bottom_ilu_factor_count") == 0
            and inventory.get("top_ilu_factor_count") == 0
            and inventory.get("global_hybrid_direct_factor_count") == 0
        )
        report = {
            "research_only": True,
            "numerical_pass": numerical_pass,
            "inventory_pass": inventory_pass,
            "pass": bool(numerical_pass and inventory_pass),
            "iterations": int(result.iterations),
            "converged_reason": int(result.converged_reason),
            "residuals": residuals,
            "inventory": inventory,
            "external_mode_count": {
                "bottom": int(bottom_components.H.getSize()[0]),
                "top": int(top_components.H.getSize()[0]),
            },
            "explicit_f_action": explicit_audit,
            "explicit_dtn_components": {
                "bottom": dict(bottom_reference.inventory["research_explicit_dtn"]),
                "top": dict(top_reference.inventory["research_explicit_dtn"]),
            },
            "solution_handoff": "not_requested",
            "reference_ownership": "owned" if reference_owned else "borrowed",
            "matrix_repeat_tolerance": float(matrix_repeat_tolerance),
        }
        if numerical_pass and inventory_pass and solution_consumer is not None:
            solution_consumer(result.solution, report)
            report["solution_handoff"] = "callback_consumed_before_cleanup"
        return report
    finally:
        if result is not None:
            result.destroy()
        if context is not None:
            context.destroy()
        if operator_context is not None:
            operator_context.destroy()
        if operator is not None:
            operator.destroy()
        if bottom_action is not None:
            bottom_action.destroy()
        if top_action is not None:
            top_action.destroy()
        if reference is not None and reference_owned:
            reference.destroy()
            reference_destroyed = True
        if report is not None:
            report["lifecycle"] = {
                "bottom_action_destroyed": bool(
                    bottom_action is not None
                    and bottom_action.diagnostics.get("destroyed") is True
                ),
                "top_action_destroyed": bool(
                    top_action is not None
                    and top_action.diagnostics.get("destroyed") is True
                ),
                "explicit_reference_destroyed": bool(reference_destroyed),
                "borrowed_reference_destroyed_by_oracle": bool(
                    not reference_owned and reference_destroyed
                ),
                "solution_consumer_synchronous": bool(
                    report.get("solution_handoff") == "callback_consumed_before_cleanup"
                ),
            }
