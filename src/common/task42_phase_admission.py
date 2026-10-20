"""Small fail-closed callback contract for Task42 Hybrid phase gates.

The callback is supplied by the public worker and is collective: every rank
must call it at the same phase boundary.  This module deliberately does not
estimate memory.  A missing/unknown byte inventory is a refusal, never zero.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

Task42PhaseGate = Callable[[str, Mapping[str, Any]], Mapping[str, Any]]

# Sizing inputs deliberately remain unresolved until the A2 mesh/NNZ/factor
# evidence exists. ``resident_J`` is sampled by the public authority at every
# phase; it is not duplicated into Delta. Sparse/factor bytes remain pending
# the actual NNZ and MUMPS INFOG/fill inventory.
TASK42_HYBRID_A2_PHASE_OBJECTS = MappingProxyType(
    {
        "public_worker_spawn": (
            "worker_python_and_mpi_initial_objects",
            "rank_local_runtime_import_and_native_context",
        ),
        "qep_cross_section_mesh": (
            "distributed_cross_section_mesh",
            "material_tags_and_coordinates",
        ),
        "qep_mixed_space": (
            "mixed_nedelec_lagrange_space",
            "collapse_maps_and_dof_ownership",
        ),
        "qep_constraints": ("dual_floquet_mpc_and_reduced_map",),
        "qep_constraint_transform": ("distributed_full_to_reduced_transform",),
        "qep_operator_K0_ffcx_form": (
            "qep_k0_ffcx_rank_payload",
            "qep_k0_ffcx_rank0_compiler_subtree",
            "qep_k0_ffcx_controller_allowance",
        ),
        "qep_operator_K0_full": (
            "full_K0_sparse_matrix",
            "qep_k0_full_controller_allowance",
        ),
        "qep_operator_K1_ffcx_form": (
            "qep_k1_ffcx_rank_payload",
            "qep_k1_ffcx_rank0_compiler_subtree",
            "qep_k1_ffcx_controller_allowance",
        ),
        "qep_operator_K1_full": (
            "full_K1_sparse_matrix",
            "qep_k1_full_controller_allowance",
        ),
        "qep_operator_K2_full": ("full_K2_sparse_matrix",),
        "qep_operator_electric_mass_full": ("full_electric_mass_sparse_matrix",),
        "qep_operator_K0_reduced": ("reduced_K0_sparse_matrix",),
        "qep_operator_K1_reduced": (
            "k1_hermitian_reduction_rank_payload",
            "qep_k1_reduction_controller_allowance",
        ),
        "qep_operator_K2_reduced": ("reduced_K2_sparse_matrix",),
        "qep_operator_electric_mass_reduced": ("reduced_electric_mass_sparse_matrix",),
        "qep_positive_eigensolve": ("slepc_pep_workspace_and_candidates",),
        "qep_positive_adjoint_eigensolve": ("positive_adjoint_pep_workspace",),
        "qep_positive_adjoint_vectors": ("positive_adjoint_distributed_mode_vectors",),
        "qep_positive_mode_vectors": ("selected_positive_distributed_mode_vectors",),
        "qep_positive_adjoint_basis": ("positive_adjoint_matrices_and_overlap_work",),
        "qep_negative_eigensolve": ("slepc_pep_workspace_and_candidates",),
        "qep_negative_adjoint_eigensolve": ("negative_adjoint_pep_workspace",),
        "qep_negative_adjoint_vectors": ("negative_adjoint_distributed_mode_vectors",),
        "qep_negative_mode_vectors": ("selected_negative_distributed_mode_vectors",),
        "qep_negative_adjoint_basis": ("negative_adjoint_matrices_and_overlap_work",),
        "local_bottom_mesh": ("bottom_endcap_mesh_and_tags",),
        "local_bottom_space": ("bottom_endcap_hcurl_space_and_mpc",),
        "local_bottom_condensed_system": (
            "bottom_condensed_matrix_rhs_and_cell_recovery_data",
        ),
        "local_bottom_dtn_augmentation": ("bottom_auxiliary_port_matrix_and_rhs",),
        "local_top_mesh": ("top_endcap_mesh_and_tags",),
        "local_top_space": ("top_endcap_hcurl_space_and_mpc",),
        "local_top_condensed_system": (
            "top_condensed_matrix_rhs_and_cell_recovery_data",
        ),
        "local_top_dtn_augmentation": ("top_auxiliary_port_matrix_and_rhs",),
        "traction_local_cell": (
            "actual_axis_matched_one_cell_mesh_space_and_local_operator",
        ),
        "traction_local_propagation": ("one_cell_propagation_and_local_mode_actions",),
        "traction_projection_and_blocks": (
            "trace_projection_and_bidirectional_traction_blocks",
        ),
        "hybrid_coupling": ("propagation_factors_and_coupling_work",),
        "hybrid_interface_blocks": ("bottom_top_coupling_block_matrices",),
        "hybrid_augmented_matrix": (
            "distributed_augmented_matrix_modal_constraint_and_maps",
        ),
        "hybrid_augmented_rhs": ("distributed_augmented_rhs_and_pack_work",),
        # PETSc KSP.setUp() currently invokes MUMPS analysis and factorization
        # together. There is no reviewed split callback between symbolic and
        # numeric phases in this direct API.
        "direct_mumps_factor_setup": (
            "mumps_symbolic_numeric_factor_and_workspace_combined",
        ),
        "direct_solve": ("direct_solve_vectors_and_mumps_work",),
        "recovery_bottom": ("bottom_local_cell_recovery_and_reduced_rhs",),
        "recovery_top": ("top_local_cell_recovery_and_reduced_rhs",),
        "field_reconstruction": ("sampled_complex_E_H_arrays_and_gather",),
        "diffraction_and_ports": ("full_external_key_fit_and_power_arrays",),
        "canonical_exports": ("canonical_prefix_vectors_and_collective_gather",),
        "output_validation_and_write": ("identity_sidecar_and_field_payload",),
        # These four phases are emitted from the existing assembly-time
        # condensation builder after it has the real local mesh, element
        # dimensions, and PETSc preallocation counts.  Their callback receives
        # that source-derived inventory instead of a guessed static Delta.
        "local_bottom_before_assembly_cell_maps_and_trace_expansion": (
            "assembly_local_cell_dof_maps",
            "assembly_cell_trace_expansion_rows",
        ),
        "local_bottom_before_task42_trace_matrix_allocation": (
            "task42_active_trace_petsc_aij_storage",
        ),
        "local_bottom_before_assembly_raw_cell_tensor_cache": (
            "assembly_unique_raw_cell_tensor_cache_and_broadcast_buffer",
        ),
        "local_bottom_before_assembly_schur_recovery_and_lu_caches": (
            "assembly_schur_recovery_lu_and_orientation_caches",
        ),
        "local_top_before_assembly_cell_maps_and_trace_expansion": (
            "assembly_local_cell_dof_maps",
            "assembly_cell_trace_expansion_rows",
        ),
        "local_top_before_task42_trace_matrix_allocation": (
            "task42_active_trace_petsc_aij_storage",
        ),
        "local_top_before_assembly_raw_cell_tensor_cache": (
            "assembly_unique_raw_cell_tensor_cache_and_broadcast_buffer",
        ),
        "local_top_before_assembly_schur_recovery_and_lu_caches": (
            "assembly_schur_recovery_lu_and_orientation_caches",
        ),
    }
)


_TASK42_COMPONENT_FORMULA_NOTES = {
    "worker_python_and_mpi_initial_objects": (
        "measure_delta_of_full_worker_tree_from_pre-spawn_J_to_imported_worker; "
        "not a fixed per-rank zero"
    ),
    "rank_local_runtime_import_and_native_context": (
        "per-rank imported Python/native state from fresh process-tree samples; "
        "scope/count must be established from the actual worker tree"
    ),
    "distributed_cross_section_mesh": (
        "owned_vertices*coordinate_bytes + owned_cells*connectivity_and_tag_bytes; "
        "counts from the resolved A2 cross-section mesh"
    ),
    "material_tags_and_coordinates": (
        "actual owned/ghost entity counts times coordinate and index dtype widths"
    ),
    "mixed_nedelec_lagrange_space": (
        "local_dofs*(scalar_bytes + index_bytes) plus element/space metadata; "
        "local_dofs from the actual p6 mesh"
    ),
    "collapse_maps_and_dof_ownership": (
        "actual local/global dof-map entries times PETSc.IntType bytes, "
        "including retained collapse maps"
    ),
    "dual_floquet_mpc_and_reduced_map": (
        "actual MPC slave/master entries times PETSc.IntType and ScalarType bytes; "
        "entry counts from the built constraints"
    ),
    "distributed_full_to_reduced_transform": (
        "nnz*(ScalarType_bytes+PetscInt_bytes)+(local_rows+1)*PetscInt_bytes; "
        "nnz and row ownership from actual transform preallocation"
    ),
    "qep_k0_ffcx_rank_payload": (
        "64MiB per actual MPI rank only for the source-checked Task42 sizing profile: "
        "36 quadrilateral cells, p6/g1, DG0/c0, q16, 4033 mixed rows, 133 mixed "
        "cell rows, complex128/Int32, MPI8; includes source-derived local cell rows, "
        "candidate pairs/tensor payload, local-to-global hash scratch, gate metadata, "
        "and predicted form/JIT/native payload. Per-rank actual counts are used; no "
        "owned-cell count is assumed. Predicted envelope, not a proven upper bound"
    ),
    "qep_k0_ffcx_rank0_compiler_subtree": (
        "512MiB rank-0 compiler process-subtree allowance, including compiler "
        "descendants; it is separate from the 64MiB rank payload and is a predicted "
        "envelope, not a measured peak or proven upper bound"
    ),
    "qep_k0_ffcx_controller_allowance": (
        "8MiB controller/receipt allowance charged once on rank 0, not once per rank"
    ),
    "full_K0_sparse_matrix": (
        "64MiB per actual MPI rank only for the same source-checked 36-cell p6/g1, "
        "DG0/c0, q16, 4033-row, MPI8 profile; basis records actual owned/ghost cell "
        "rows, candidate pairs, local tensor bytes, diagonal/off-diagonal candidate "
        "payload, remote-row stash, PETSc row pointers, remote-column allowance, "
        "layout-hash scratch, and gate metadata. Includes these listed payloads and "
        "un-calibrated PETSc/native workspace; predicted envelope, not a hard bound"
    ),
    "qep_k0_full_controller_allowance": (
        "8MiB controller/receipt allowance charged once on rank 0, not once per rank"
    ),
    "qep_k1_ffcx_rank_payload": (
        "64MiB per actual rank for the source-checked 36-cell p6/g1, DG0/c0, q16, "
        "4033-row MPI8 profile; includes the live source-basis/form inventory and "
        "un-calibrated FFCx/PETSc-side rank workspace; predicted, not a hard bound"
    ),
    "qep_k1_ffcx_rank0_compiler_subtree": (
        "512MiB compiler-subtree allowance on rank 0, including compiler descendants; "
        "predicted, not a measured peak or proven upper bound"
    ),
    "qep_k1_ffcx_controller_allowance": (
        "8MiB controller/receipt allowance charged once on rank 0"
    ),
    "full_K1_sparse_matrix": (
        "64MiB per rank only for the source-checked 36-cell p6/g1, DG0/c0, q16, "
        "4033-row MPI8 profile; source basis includes local cell tensors and the "
        "global 36*133^2 sparse contribution bound per rank, row pointers, remote "
        "columns/stash, and inventory metadata; predicted, not a hard bound or "
        "measured K1 MatInfo"
    ),
    "qep_k1_full_controller_allowance": (
        "8MiB controller/receipt allowance charged once on rank 0"
    ),
    "k1_hermitian_reduction_rank_payload": (
        "Per-rank source-derived peak: max(pre-product support-inventory scratch, "
        "including one bounded input getRow row-scan temporary, simultaneous "
        "C^H/K1*C/reduced-K1 candidate sparse payload with row pointers, remote-column "
        "arrays and redistribution/stash). Inventory scratch is released before "
        "products are created; no output-CSR copy is made in the gate. Computed from "
        "current K1/C CSR and actual ownership, refused above 64MiB. Native MatMatMult "
        "workspace remains uncalibrated, so this is a predicted envelope, not a hard bound"
    ),
    "qep_k1_reduction_controller_allowance": (
        "8MiB controller/receipt allowance charged once on rank 0"
    ),
    "full_K2_sparse_matrix": "AIJ_nnz*(ScalarType_bytes+PetscInt_bytes)+(local_rows+1)*PetscInt_bytes",
    "full_electric_mass_sparse_matrix": "AIJ_nnz*(ScalarType_bytes+PetscInt_bytes)+(local_rows+1)*PetscInt_bytes",
    "reduced_K0_sparse_matrix": "AIJ_nnz*(ScalarType_bytes+PetscInt_bytes)+(local_rows+1)*PetscInt_bytes",
    "reduced_K1_sparse_matrix": "AIJ_nnz*(ScalarType_bytes+PetscInt_bytes)+(local_rows+1)*PetscInt_bytes",
    "reduced_K2_sparse_matrix": "AIJ_nnz*(ScalarType_bytes+PetscInt_bytes)+(local_rows+1)*PetscInt_bytes",
    "reduced_electric_mass_sparse_matrix": "AIJ_nnz*(ScalarType_bytes+PetscInt_bytes)+(local_rows+1)*PetscInt_bytes",
    "slepc_pep_workspace_and_candidates": (
        "pending actual SLEPc PEP dimensions, ncv/mpd, retained candidates, "
        "and backend workspace; no A1 factor peak substitution"
    ),
    "positive_adjoint_pep_workspace": "pending actual adjoint PEP dimensions and backend workspace",
    "positive_adjoint_distributed_mode_vectors": (
        "candidate_count*local_dofs*complex128_bytes, plus any simultaneous work vectors"
    ),
    "selected_positive_distributed_mode_vectors": (
        "selected_count*local_dofs*complex128_bytes, plus any simultaneous work vectors"
    ),
    "positive_adjoint_matrices_and_overlap_work": (
        "sparse NNZ formula for retained operators plus actual overlap matrix dimensions; "
        "backend temporary workspace pending"
    ),
    "negative_adjoint_pep_workspace": "pending actual adjoint PEP dimensions and backend workspace",
    "negative_adjoint_distributed_mode_vectors": (
        "candidate_count*local_dofs*complex128_bytes, plus any simultaneous work vectors"
    ),
    "negative_adjoint_matrices_and_overlap_work": (
        "sparse NNZ formula for retained operators plus actual overlap matrix dimensions; "
        "backend temporary workspace pending"
    ),
    "bottom_endcap_mesh_and_tags": "actual owned mesh entities times coordinate/connectivity/tag dtype widths",
    "bottom_endcap_hcurl_space_and_mpc": (
        "actual local dof maps plus MPC slave/master rows; index and scalar widths from ABI"
    ),
    "bottom_condensed_matrix_rhs_and_cell_recovery_data": (
        "actual Schur AIJ NNZ storage plus cell-class tensor/LU/recovery arrays; "
        "class and NNZ counts from this mesh"
    ),
    "bottom_auxiliary_port_matrix_and_rhs": (
        "actual auxiliary mode rows and nonzero couplings times ScalarType/PetscInt widths"
    ),
    "top_endcap_mesh_and_tags": "actual owned mesh entities times coordinate/connectivity/tag dtype widths",
    "top_endcap_hcurl_space_and_mpc": (
        "actual local dof maps plus MPC slave/master rows; index and scalar widths from ABI"
    ),
    "top_condensed_matrix_rhs_and_cell_recovery_data": (
        "actual Schur AIJ NNZ storage plus cell-class tensor/LU/recovery arrays; "
        "class and NNZ counts from this mesh"
    ),
    "top_auxiliary_port_matrix_and_rhs": (
        "actual auxiliary mode rows and nonzero couplings times ScalarType/PetscInt widths"
    ),
    "actual_axis_matched_one_cell_mesh_space_and_local_operator": (
        "actual one-cell mesh, local dofs, and sparse/local tensor dimensions; "
        "axis match is validated by the builder"
    ),
    "one_cell_propagation_and_local_mode_actions": (
        "actual mode count times local action workspace; count and dtype from resolved keys"
    ),
    "trace_projection_and_bidirectional_traction_blocks": (
        "actual projection/block shapes times ScalarType bytes and retained copies; "
        "mode and trace counts from the run"
    ),
    "propagation_factors_and_coupling_work": (
        "actual selected modes times retained forward/backward complex factors and work arrays"
    ),
    "bottom_top_coupling_block_matrices": (
        "actual block rows/columns and NNZ times ScalarType/PetscInt storage widths"
    ),
    "distributed_augmented_matrix_modal_constraint_and_maps": (
        "augmented_AIJ_nnz*(ScalarType_bytes+PetscInt_bytes)+(local_rows+1)*PetscInt_bytes; "
        "includes only PETSc-allocated sparse storage and explicit maps"
    ),
    "distributed_augmented_rhs_and_pack_work": (
        "local_augmented_rows*complex128_bytes per live vector; simultaneous pack/copy count "
        "must be derived from the actual solve path"
    ),
    "mumps_symbolic_numeric_factor_and_workspace_combined": (
        "pending actual MUMPS INFOG/fill/workspace evidence; PETSc KSP.setUp currently "
        "combines analysis and factorization, so this gate covers their combined setup"
    ),
    "direct_solve_vectors_and_mumps_work": (
        "actual local augmented rows*complex128_bytes per live vector plus solver workspace; "
        "vector count and factor workspace require source/bridge evidence"
    ),
    "bottom_local_cell_recovery_and_reduced_rhs": (
        "actual owned cell recovery matrices, local RHS, and recovered vectors; "
        "shape/dtype/count from local recovery maps"
    ),
    "top_local_cell_recovery_and_reduced_rhs": (
        "actual owned cell recovery matrices, local RHS, and recovered vectors; "
        "shape/dtype/count from local recovery maps"
    ),
    "sampled_complex_E_H_arrays_and_gather": (
        "Nx*Ny*Nz*3*complex128_bytes per field plus live gather/serialization copies; "
        "Nx/Ny/Nz from actual sample_x/y/z"
    ),
    "full_external_key_fit_and_power_arrays": (
        "actual_external_key_count*complex128_bytes per fit/power vector plus retained "
        "metadata and any simultaneously live copies"
    ),
    "canonical_prefix_vectors_and_collective_gather": (
        "actual canonical vector lengths*complex128_bytes plus gather/send buffers; "
        "MPI ownership and copies must be inventoried"
    ),
    "identity_sidecar_and_field_payload": (
        "actual payload array nbytes plus bounded compression/serialization workspace; "
        "writer implementation and simultaneous copy count must be measured"
    ),
}


_TASK42_DYNAMIC_ASSEMBLY_FORMULAS = {
    "assembly_local_cell_dof_maps": (
        "owned_cells*element_dimension*(int32_bytes+PetscInt_bytes)"
    ),
    "assembly_cell_trace_expansion_rows": (
        "owned_cells*trace_dimension*(2*PetscInt_bytes+24)"
    ),
    "task42_active_trace_petsc_aij_storage": (
        "allocated_nnz*(ScalarType_bytes+PetscInt_bytes)+(local_rows+1)*PetscInt_bytes"
    ),
    "assembly_unique_raw_cell_tensor_cache_and_broadcast_buffer": (
        "2*local_geometry_class_count*element_dimension^2*ScalarType_bytes"
    ),
    "assembly_schur_recovery_lu_and_orientation_caches": (
        "class_count*per_class_complex_entries*ScalarType_bytes+pivot_count*PetscInt_bytes+identity_entries*float64_bytes"
    ),
}


def task42_pending_phase_inventory(
    phase: str,
    component_names: tuple[str, ...],
    *,
    allocation_boundary: str,
    lifetime: str,
    scope: str = "rank_local",
) -> dict[str, Any]:
    """Describe a real allocation boundary whose Task42 size is not yet known."""

    if not phase or not allocation_boundary or not lifetime or not component_names:
        raise ValueError("Task42 phase inventory requires complete boundary identity")
    components = []
    for name in component_names:
        components.append(
            {
                "name": name,
                "scope": scope,
                "unit": "bytes",
                "delta_bytes": None,
                "formula": _TASK42_COMPONENT_FORMULA_NOTES.get(
                    name,
                    "pending source-derived shape/NNZ/fill inventory; not a fixed constant",
                ),
                "lifetime": lifetime,
                "allocation_boundary": allocation_boundary,
                "resident_J_source": "fresh whole-job authority; not part of Delta",
                "sizing_basis": _TASK42_COMPONENT_FORMULA_NOTES.get(
                    name,
                    "pending actual source arrays, mesh/NNZ/factor fill, and copy count",
                ),
                "uncertainty": (
                    "not yet measured or conservatively estimated; all overlapping "
                    "live objects and backend workspace must be resolved"
                ),
                "estimated_delta_role": "pending-sizing; not zero and not A1-derived",
            }
        )
    return {
        "status": "pending-sizing",
        "phase": phase,
        "allocation_boundary": allocation_boundary,
        "lifetime": lifetime,
        "components": components,
    }


def task42_phase_inventory(phase: str) -> dict[str, Any]:
    """Return the static object list for one phase, with all bytes pending."""

    try:
        components = TASK42_HYBRID_A2_PHASE_OBJECTS[str(phase)]
    except KeyError as exc:
        raise ValueError(f"unknown Task42 Hybrid phase {phase!r}") from exc
    allocation_boundary = str(phase)
    for side in ("bottom", "top"):
        prefix = f"local_{side}_"
        if allocation_boundary.startswith(prefix):
            allocation_boundary = allocation_boundary[len(prefix) :]
            break
    return task42_pending_phase_inventory(
        str(phase),
        components,
        allocation_boundary=allocation_boundary,
        lifetime="phase-specific; exact overlap pending sizing/lifecycle evidence",
    )


def require_task42_phase_admission(
    callback: Task42PhaseGate | None,
    phase: str,
    inventory: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Require a unanimous public-worker admission before allocating objects."""

    if not callable(callback):
        raise TypeError(f"Task42 phase {phase} has no resource gate callback")
    decision = callback(phase, inventory)
    if not isinstance(decision, Mapping) or decision.get("pass") is not True:
        errors = decision.get("errors") if isinstance(decision, Mapping) else None
        raise RuntimeError(
            f"Task42 phase {phase} refused before allocation: {errors or 'missing gate receipt'}"
        )
    return decision


def task42_assembly_stage_gate_adapter(
    callback: Task42PhaseGate, *, side: str
):
    """Adapt the condensation builder's ``(stage, bytes, inventory)`` hook.

    The builder calculates these component sizes from its actual local mesh,
    finite-element dimensions, and PETSc preallocation.  The normalized
    inventory retains those values so the worker can compare each rank's
    measured/source-derived Delta to the identity-bound manifest before the
    allocation.  Unknown or malformed components are forwarded as refusal
    evidence to the collective worker gate rather than locally raising before
    peers reach the same collective.
    """

    if not callable(callback):
        raise TypeError("Task42 assembly stage adapter requires a callback")
    if side not in {"bottom", "top"}:
        raise ValueError("Task42 assembly stage adapter requires bottom/top side")

    def gate(stage: str, local_delta_bytes: int, inventory: Mapping[str, Any]):
        phase = f"local_{side}_{stage}"
        errors: list[str] = []
        raw_components = inventory.get("components")
        normalized_components: list[dict[str, Any]] = []
        local_sum = 0
        if not isinstance(raw_components, list) or not raw_components:
            errors.append("source_assembly_components_are_missing")
            raw_components = []
        for index, component in enumerate(raw_components):
            if not isinstance(component, Mapping):
                errors.append(f"source_assembly_component_{index}_is_not_a_mapping")
                continue
            name = component.get("name")
            scope = component.get("scope")
            amount = component.get("delta_bytes")
            formula = _TASK42_DYNAMIC_ASSEMBLY_FORMULAS.get(str(name))
            if not isinstance(name, str) or name not in _TASK42_DYNAMIC_ASSEMBLY_FORMULAS:
                errors.append(f"source_assembly_component_{index}_name_is_unknown")
                continue
            if scope != "rank_local":
                errors.append(f"source_assembly_component_{name}_scope_is_not_rank_local")
            if type(amount) is not int or amount < 0:
                errors.append(f"source_assembly_component_{name}_Delta_is_invalid")
            else:
                local_sum += amount
            basis = component.get("basis")
            normalized_components.append(
                {
                    "name": name,
                    "scope": scope,
                    "unit": component.get("unit"),
                    "delta_bytes": amount,
                    "formula": formula,
                    "lifetime": (
                        "source-derived local assembly allocation; retained/released "
                        "within the current condensation builder call; exact overlap "
                        "with neighboring objects remains part of sizing review"
                    ),
                    "allocation_boundary": stage,
                    "phase": phase,
                    "resident_J_source": "fresh whole-job authority; not part of Delta",
                    "sizing_basis": dict(basis) if isinstance(basis, Mapping) else None,
                    "classification": component.get("classification"),
                    "upper_bound_proven": component.get("upper_bound_proven") is True,
                }
            )
        if type(local_delta_bytes) is not int or local_delta_bytes < 0:
            errors.append("source_assembly_local_Delta_is_invalid")
        elif local_sum != local_delta_bytes:
            errors.append("source_assembly_component_sum_does_not_match_local_Delta")
        normalized = {
            "schema": "task42.direct_phase_delta_inventory.v1",
            "status": "source-derived-prediction",
            "phase": phase,
            "side": side,
            "allocation_boundary": stage,
            "lifetime": "source-derived local assembly phase; overlap pending review",
            "resident_J_source": "fresh whole-job authority; not part of Delta",
            "estimate_uncertainty": inventory.get("estimate_uncertainty"),
            "evidence": inventory.get("evidence"),
            "components": normalized_components,
            "admission_errors": errors,
        }
        return callback(phase, normalized)

    return gate


def admit_task42_phase(callback: Task42PhaseGate | None, phase: str) -> Mapping[str, Any] | None:
    """Run a named preallocation gate when the Task42 opt-in is active."""

    if callback is None:
        return None
    return require_task42_phase_admission(callback, phase, task42_phase_inventory(phase))


__all__ = [
    "TASK42_HYBRID_A2_PHASE_OBJECTS",
    "Task42PhaseGate",
    "admit_task42_phase",
    "require_task42_phase_admission",
    "task42_assembly_stage_gate_adapter",
    "task42_pending_phase_inventory",
    "task42_phase_inventory",
]
