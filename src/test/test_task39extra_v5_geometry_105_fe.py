"""Bounded real-FE qualification of the V5 rounded tensor representative."""

from __future__ import annotations

import hashlib
import json
import os
import time
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from mpi4py import MPI

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/task39extra_para_workstation_capacity/v5_node1_5nm_p6h4_q4.dat"


@unittest.skipUnless(
    os.environ.get("TASK39EXTRA_RUN_V5_GEOMETRY_105_FE") == "1"
    and os.environ.get("TASK39EXTRA_PORD64_ROOT"),
    "requires explicit task-local PORD64 activation",
)
class Task39ExtraV5Geometry105FETests(unittest.TestCase):
    def test_raw_and_rounded_tensor_groups_on_real_5nm_105_cell_fe_mpc(self):
        from dolfinx.la.petsc import create_vector
        from petsc4py import PETSc

        from src.io import load_and_resolve
        from src.io.input_validation import simulation_config_3d_from_normalized
        from src.runners.physical_retained_condensed_v20 import (
            RetainedCondensedRuntime,
            _compile_volume_form,
            _native_aq_projection_check,
            _support_groups,
        )
        from src.solvers.fullspace_dtn_action import (
            build_dynamic_mode_inventory,
            build_ordered_mode_manifest,
        )
        from src.solvers.fullspace_physical_intermediate_runtime import (
            AlgebraicOwnerTransfer,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg import (
            build_same_mesh_hcurl_transfer,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
            _build_same_mesh_levels,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            build_same_mesh_physical_action,
            destroy_same_mesh_physical_action,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
            build_same_mesh_hcurl_owner_transfer,
        )
        from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
        from src.solvers.hcurl_assembly_time_condensation import (
            _canonical_axis_aligned_coordinates,
            _cell_integral_kernels,
            _cell_tag_array,
            _lexicographic_min_coordinates,
            _tabulate_raw_tensor_class,
            build_unconstrained_assembly_time_condensation,
        )
        from src.solvers.p4_cell_condensed_inverse import (
            P4CellCondensedInverse,
            P4RefinementLedger,
            assemble_condensed_ports,
        )
        from src.solvers.p6_cell_condensed_action import (
            build_p6_cell_condensed_action_from_carrier,
        )

        specification = load_and_resolve(INPUT)
        cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
        small_cfg = replace(
            cfg,
            mesh_axis_cell_counts=(5, 3, 7),
            mesh_axis_x_values=None,
            mesh_axis_y_values=None,
            mesh_axis_z_values=None,
            mesh_axis_z_profile=None,
            mesh_plan_id=None,
            mesh_plan_sha256=None,
        )
        self.assertEqual(int(np.prod(small_cfg.mesh_axis_cell_counts)), 105)
        self.assertEqual(int(MPI.COMM_SELF.size), 1)

        levels = _build_same_mesh_levels(
            small_cfg,
            MPI.COMM_SELF,
            (6, 4),
            include_positive_coefficients=True,
        )
        fine = coarse = owner = local_transfer = None
        cases = {}
        inverses = []
        owned_vectors = []
        try:
            full_modes, _full_rows, full_mode_sha = build_dynamic_mode_inventory(
                small_cfg
            )
            zero_modes = tuple(
                mode for mode in full_modes if mode.m == 0 and mode.n == 0
            )
            self.assertEqual(len(full_modes), 600)
            self.assertEqual(len(zero_modes), 4)
            mode_rows, _encoded, mode_sha = build_ordered_mode_manifest(
                zero_modes, small_cfg
            )
            selected_modes = (zero_modes, mode_rows, mode_sha)
            fine = build_same_mesh_physical_action(
                levels, small_cfg, 6, mode_inventory=selected_modes
            )
            coarse = build_same_mesh_physical_action(
                levels, small_cfg, 4, mode_inventory=selected_modes
            )
            compiled = {
                degree: _compile_volume_form(bundle["volume_action"])
                for degree, bundle in ((6, fine), (4, coarse))
            }

            mesh = levels["mesh_data"].mesh
            cell_count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
            self.assertEqual(cell_count, 105)
            tags = _cell_tag_array(levels["mesh_data"].cell_tags, cell_count)
            raw_coordinates = {}
            members_by_group = {}
            for cell in range(cell_count):
                canonical, widths = _canonical_axis_aligned_coordinates(
                    mesh,
                    cell,
                    tolerance=1.0e-11,
                    geometry_identity_policy="raw_unrounded",
                )
                tag = int(tags[cell])
                raw_key = (tag, *widths)
                previous = raw_coordinates.get(raw_key)
                if previous is not None:
                    np.testing.assert_array_equal(previous, canonical)
                raw_coordinates.setdefault(raw_key, canonical)
                group_key = (
                    "actual_space",
                    tag,
                    *(float(np.round(width, 12)) for width in widths),
                )
                members_by_group.setdefault(group_key, {})[raw_key] = canonical

            raw_class_count = len(raw_coordinates)
            tensor_group_count = len(members_by_group)
            self.assertLessEqual(tensor_group_count, raw_class_count)
            self.assertGreater(raw_class_count - tensor_group_count, 0)

            tensor_comparisons = {}
            representatives = {}
            tensor_validation_seconds = {}
            for degree in (6, 4):
                kernels = _cell_integral_kernels(
                    compiled[degree], sum_duplicate_cell_integrals=True
                )
                dimension = int(levels["spaces"][degree].element.space_dimension)
                worst_relative = -1.0
                worst_absolute = 0.0
                worst_identity = None
                rep_rows = []
                validation_started = time.perf_counter()
                for group_key, raw_members in sorted(members_by_group.items()):
                    representative = None
                    for coordinates in raw_members.values():
                        representative = (
                            coordinates
                            if representative is None
                            else _lexicographic_min_coordinates(
                                representative, coordinates
                            )
                        )
                    assert representative is not None
                    representative_hash = hashlib.sha256(
                        np.ascontiguousarray(representative, dtype=np.float64).tobytes()
                    ).hexdigest()
                    representative_tensor = _tabulate_raw_tensor_class(
                        compiled[degree],
                        kernels,
                        representative,
                        tag=int(group_key[1]),
                        dimension=dimension,
                    )
                    rep_rows.append(
                        {
                            "material_tag": int(group_key[1]),
                            "rounded_width_key": [float(v) for v in group_key[2:]],
                            "canonical_coordinates": representative.reshape(8, 3).tolist(),
                            "canonical_coordinates_sha256": representative_hash,
                            "raw_member_count": len(raw_members),
                        }
                    )
                    for raw_key, raw_coords in raw_members.items():
                        raw_tensor = _tabulate_raw_tensor_class(
                            compiled[degree],
                            kernels,
                            raw_coords,
                            tag=int(raw_key[0]),
                            dimension=dimension,
                        )
                        difference = representative_tensor - raw_tensor
                        absolute = float(np.linalg.norm(difference))
                        relative = absolute / max(
                            float(np.linalg.norm(raw_tensor)),
                            np.finfo(np.float64).tiny,
                        )
                        if relative > worst_relative:
                            worst_relative = relative
                            worst_absolute = absolute
                            worst_identity = {
                                "material_tag": int(raw_key[0]),
                                "raw_widths": [float(v) for v in raw_key[1:]],
                                "raw_canonical_coordinates_sha256": hashlib.sha256(
                                    np.ascontiguousarray(
                                        raw_coords, dtype=np.float64
                                    ).tobytes()
                                ).hexdigest(),
                                "representative_coordinates_sha256": representative_hash,
                            }
                        del raw_tensor, difference
                    del representative_tensor
                tensor_validation_seconds[str(degree)] = (
                    time.perf_counter() - validation_started
                )
                representatives[str(degree)] = rep_rows
                tensor_comparisons[str(degree)] = {
                    "raw_geometry_class_count": raw_class_count,
                    "tensor_group_count": tensor_group_count,
                    "max_group_representative_tensor_relative_difference": max(
                        0.0, worst_relative
                    ),
                    "max_group_representative_tensor_absolute_difference": worst_absolute,
                    "worst_raw_class_vs_representative": worst_identity,
                    "comparison_scope": "all unique real FE geometry classes, streamed one tensor at a time",
                }
                self.assertLessEqual(max(0.0, worst_relative), 1.0e-6)

            for policy in ("raw_unrounded", "rounded_12_representative"):
                p6_started = time.perf_counter()
                p6_system = build_unconstrained_assembly_time_condensation(
                    compiled[6],
                    levels["spaces"][6],
                    levels["mesh_data"].cell_tags,
                    mpc=levels["floquets"][6].mpc,
                    appended_global_rows=len(fine["dtn_action"].carrier.entries),
                    materialize_global_matrix=False,
                    retain_local_schur_for_matrix_free=True,
                    sum_duplicate_cell_integrals=True,
                    strict_local_checks=True,
                    geometry_identity_policy=policy,
                    share_identity_cache=True,
                )
                p6_elapsed = time.perf_counter() - p6_started
                p6_action = build_p6_cell_condensed_action_from_carrier(
                    p6_system,
                    fine["dtn_action"].carrier,
                    owns_condensed=True,
                )

                p4_started = time.perf_counter()
                groups, group_by_row = _support_groups(
                    levels["spaces"][4], coarse["dtn_action"].carrier
                )
                p4_system = build_unconstrained_assembly_time_condensation(
                    compiled[4],
                    levels["spaces"][4],
                    levels["mesh_data"].cell_tags,
                    mpc=levels["floquets"][4].mpc,
                    appended_global_rows=len(coarse["dtn_action"].carrier.entries),
                    appended_support_owned_cell_groups=groups,
                    appended_support_group_by_row=group_by_row,
                    dense_appended_block=True,
                    sum_duplicate_cell_integrals=True,
                    strict_local_checks=True,
                    defer_final_assembly=True,
                    geometry_identity_policy=policy,
                    share_identity_cache=True,
                )
                p4_terms = assemble_condensed_ports(
                    p4_system, coarse["dtn_action"].carrier
                )
                p4_system.matrix.assemble()
                p4_elapsed = time.perf_counter() - p4_started
                cases[policy] = {
                    "p6_system": p6_system,
                    "p6_action": p6_action,
                    "p4_system": p4_system,
                    "p4_terms": p4_terms,
                    "p6_wall_seconds": p6_elapsed,
                    "p4_wall_seconds": p4_elapsed,
                }

            expected_oriented_classes = {}
            for degree, key in ((6, "p6_system"), (4, "p4_system")):
                raw_system = cases["raw_unrounded"][key]
                candidate_system = cases["rounded_12_representative"][key]
                raw_audit = raw_system.build_audit
                candidate_audit = candidate_system.build_audit
                self.assertEqual(
                    candidate_audit["raw_geometry_class_count_global_unique"],
                    raw_class_count,
                )
                self.assertEqual(
                    candidate_audit["tensor_group_count_global_unique"],
                    tensor_group_count,
                )
                self.assertEqual(
                    raw_audit["raw_tensor_class_count_global_unique"],
                    raw_class_count,
                )
                self.assertEqual(
                    raw_audit["oriented_schur_class_count_sum"],
                    candidate_audit["oriented_schur_class_count_sum"],
                )
                expected_oriented_classes[str(degree)] = int(
                    raw_audit["oriented_schur_class_count_sum"]
                )
                self.assertEqual(
                    candidate_audit["schur_lu_recovery_cache_key"],
                    "raw_float64_widths_plus_orientation",
                )
                self.assertTrue(candidate_audit["mpc_expansion_applied_per_cell"])
                recorded_reps = {
                    (
                        int(row["material_tag"]),
                        *(float(value) for value in row["cell_widths"]),
                    ): row["canonical_coordinates_sha256"]
                    for row in candidate_audit["raw_tensor_classes"]
                }
                for row in representatives[str(degree)]:
                    key_tuple = (row["material_tag"], *row["rounded_width_key"])
                    self.assertEqual(
                        recorded_reps[key_tuple],
                        row["canonical_coordinates_sha256"],
                    )

            # The independent original A6 action and its recovered-field
            # residual are evaluated on exactly the same real-FE/MPC input.
            p6_space = levels["spaces"][6]
            p6_full_rows = cases["raw_unrounded"]["p6_system"].full_rows
            interior = np.unique(
                np.concatenate(
                    [
                        cell.interior_original_dofs
                        for cell in cases["raw_unrounded"]["p6_system"].cell_recovery_maps
                    ]
                )
            )
            p6_rhs = np.zeros(p6_full_rows, dtype=np.complex128)
            index = interior.astype(np.float64) + 1.0
            p6_rhs[interior] = np.sin(0.071 * index) + 1j * np.cos(0.043 * index)
            self.assertGreater(float(np.linalg.norm(p6_rhs[interior])), 0.0)
            explicit_port_rhs = np.asarray(
                [0.17 + 0.23j, -0.31 + 0.11j, 0.29 - 0.19j, -0.07 - 0.37j],
                dtype=np.complex128,
            )
            self.assertGreater(float(np.linalg.norm(explicit_port_rhs)), 0.0)
            reduced_vector = np.arange(
                cases["raw_unrounded"]["p6_action"].reduced_size,
                dtype=np.float64,
            )
            reduced_vector = np.sin(0.031 * (reduced_vector + 1.0)) + 1j * np.cos(
                0.017 * (reduced_vector + 1.0)
            )
            raw_p6_output = cases["raw_unrounded"]["p6_action"].apply(
                reduced_vector
            )
            candidate_p6_output = cases["rounded_12_representative"][
                "p6_action"
            ].apply(reduced_vector)
            p6_action_relative = float(
                np.linalg.norm(candidate_p6_output - raw_p6_output)
                / max(np.linalg.norm(raw_p6_output), np.finfo(float).tiny)
            )

            native_a6_calls = 0

            def native_a6_apply(values):
                nonlocal native_a6_calls
                nonlocal_source = create_vector(
                    [
                        (
                            p6_space.dofmap.index_map,
                            int(p6_space.dofmap.index_map_bs),
                        )
                    ]
                )
                nonlocal_target = nonlocal_source.duplicate()
                try:
                    nonlocal_source.array[:] = np.asarray(values, dtype=np.complex128)
                    fine["physical_action"].apply(nonlocal_source, nonlocal_target)
                    native_a6_calls += 1
                    return np.asarray(
                        nonlocal_target.getArray(readonly=True), dtype=np.complex128
                    ).copy()
                finally:
                    nonlocal_target.destroy()
                    nonlocal_source.destroy()

            p6_native_facts = {}
            for policy, case in cases.items():
                p6_native_facts[policy] = case["p6_action"].evaluate_native_residual(
                    reduced_vector,
                    p6_rhs,
                    native_a6_apply,
                    port_rhs=explicit_port_rhs,
                    rhs_is_mpc_dual=True,
                )
                self.assertLessEqual(
                    p6_native_facts[policy]["native_identity_relative"], 1.0e-10
                )
                self.assertLessEqual(
                    p6_native_facts[policy]["schur_port_identity_relative"], 1.0e-10
                )
            raw_native_residual = p6_native_facts["raw_unrounded"]["native_residual"]
            candidate_native_residual = p6_native_facts[
                "rounded_12_representative"
            ]["native_residual"]
            a6_action_relative = float(
                np.linalg.norm(candidate_native_residual - raw_native_residual)
                / max(
                    np.linalg.norm(p6_native_facts["raw_unrounded"]["native_effective_rhs"]),
                    np.linalg.norm(raw_native_residual),
                    np.finfo(float).tiny,
                )
            )

            local_transfer = build_same_mesh_hcurl_transfer(6, 4)
            owner = build_same_mesh_hcurl_owner_transfer(
                levels["spaces"][6],
                levels["floquets"][6],
                levels["spaces"][4],
                levels["floquets"][4],
                local_transfer=local_transfer,
                fixed_serial_owner_route=True,
                optimized_owner_apply=True,
            )
            transfer = AlgebraicOwnerTransfer(owner)
            aq_runtime = SimpleNamespace(
                levels=levels,
                coarse_degree=4,
                transfer=transfer,
                fine=fine,
                p4=coarse,
            )
            aq = _native_aq_projection_check(aq_runtime)
            self.assertTrue(aq["passed"])
            aq_volume_relative = float(
                aq["native_Aq_volume_vs_PqH_A6_volume_P"]["relative"]
            )
            aq_dtn_relative = float(
                aq["native_Aq_DtN_vs_PqH_A6_DtN_P"]["relative"]
            )
            self.assertLessEqual(aq_volume_relative, 1.0e-10)
            self.assertLessEqual(aq_dtn_relative, 1.0e-10)

            p4_rhs_norms = {}
            p4_residuals = {}
            p4_solution_by_policy = {}
            p4_augmented_port_residuals = {}
            PETSc.Options()["mat_mumps_icntl_7"] = 4
            try:
                for policy, case in cases.items():
                    system = case["p4_system"]
                    factor = _MumpsFactor(system.matrix)
                    factor.set_icntl(23, 0)
                    factor.symbolic(system.matrix)
                    factor.numeric(system.matrix)
                    self.assertEqual(factor.get_icntl(23), 0)
                    self.assertEqual(int(factor.info((1,))["infog"]["1"]), 0)
                    self.assertEqual(int(factor.info((7,))["infog"]["7"]), 4)
                    inverse = P4CellCondensedInverse(
                        system,
                        factor,
                        port_terms=case["p4_terms"],
                        owns_factor=True,
                        owns_condensed=True,
                        retain_through_postprocess_v18=False,
                    )
                    factor = None
                    inverses.append(inverse)
                    proxy = SimpleNamespace(p4=coarse, p4_system=system)
                    ledger = P4RefinementLedger(
                        inverse,
                        lambda c, a, _proxy=proxy: RetainedCondensedRuntime.apply_original_a4(
                            _proxy, c, a
                        ),
                        port_closure=lambda c, a, _proxy=proxy: RetainedCondensedRuntime.port_closure(
                            _proxy, c, a
                        ),
                        max_refinements=2,
                    )
                    full_rhs = PETSc.Vec().createMPI(
                        (system.full_rows, system.full_rows), comm=MPI.COMM_SELF
                    )
                    owned_vectors.append(full_rhs)
                    interior_p4 = np.unique(
                        np.concatenate(
                            [cell.interior_original_dofs for cell in system.cell_recovery_maps]
                        )
                    )
                    rhs_indices = interior_p4.astype(np.float64) + 1.0
                    full_rhs.getArray()[interior_p4] = np.sin(
                        0.029 * rhs_indices
                    ) + 1j * np.cos(0.037 * rhs_indices)
                    full_rhs.assemble()
                    p4_rhs_norms[policy] = float(
                        np.linalg.norm(full_rhs.getValues(interior_p4))
                    )
                    self.assertGreater(p4_rhs_norms[policy], 0.0)
                    returned = ledger.solve(full_rhs)
                    owned_vectors.append(returned)
                    audit = ledger.last_audit
                    self.assertEqual(audit["status"], "P4_RETURN_PASS")
                    residual = float(audit["rows"][-1]["relative_residual"])
                    self.assertLessEqual(residual, 1.0e-10)
                    self.assertLessEqual(int(audit["refinement_count"]), 2)
                    self.assertEqual(audit["rows"][-1]["port_closure"]["status"], "PASS")
                    p4_residuals[policy] = residual
                    p4_solution_by_policy[policy] = np.asarray(
                        returned.getArray(readonly=True), dtype=np.complex128
                    ).copy()

                    reduced_rhs = inverse._reduce_storage_rhs(full_rhs)
                    owned_vectors.append(reduced_rhs)
                    reduced_values = reduced_rhs.getArray()
                    self.assertEqual(
                        reduced_values.size,
                        int(system.active_rows + system.appended_rows),
                    )
                    reduced_values[system.active_rows :] += explicit_port_rhs
                    port_solution = inverse._solve_once(reduced_rhs)
                    owned_vectors.append(port_solution)
                    matrix_residual = reduced_rhs.duplicate()
                    owned_vectors.append(matrix_residual)
                    system.matrix.mult(port_solution, matrix_residual)
                    matrix_residual.axpy(PETSc.ScalarType(-1.0), reduced_rhs)
                    p4_augmented_port_residuals[policy] = float(
                        matrix_residual.norm()
                        / max(reduced_rhs.norm(), np.finfo(float).tiny)
                    )
                    self.assertLessEqual(
                        p4_augmented_port_residuals[policy], 1.0e-10
                    )
                    ledger.last_audit.clear()
            finally:
                del PETSc.Options()["mat_mumps_icntl_7"]

            p4_solution_relative = float(
                np.linalg.norm(
                    p4_solution_by_policy["rounded_12_representative"]
                    - p4_solution_by_policy["raw_unrounded"]
                )
                / max(
                    np.linalg.norm(p4_solution_by_policy["raw_unrounded"]),
                    np.finfo(float).tiny,
                )
            )
            p4_matrix_relative = {}
            raw_system = cases["raw_unrounded"]["p4_system"]
            candidate_system = cases["rounded_12_representative"]["p4_system"]
            matrix_input = raw_system.matrix.createVecRight()
            matrix_output_raw = raw_system.matrix.createVecLeft()
            matrix_output_candidate = candidate_system.matrix.createVecLeft()
            owned_vectors.extend((matrix_input, matrix_output_raw, matrix_output_candidate))
            matrix_indices = np.arange(matrix_input.getLocalSize(), dtype=np.float64)
            matrix_input.getArray()[:] = np.sin(0.019 * (matrix_indices + 1.0)) + 1j * np.cos(
                0.023 * (matrix_indices + 1.0)
            )
            raw_system.matrix.mult(matrix_input, matrix_output_raw)
            candidate_system.matrix.mult(matrix_input, matrix_output_candidate)
            matrix_output_candidate.axpy(
                PETSc.ScalarType(-1.0), matrix_output_raw
            )
            p4_matrix_relative["nonzero_complex_action"] = float(
                matrix_output_candidate.norm()
                / max(matrix_output_raw.norm(), np.finfo(float).tiny)
            )

            self.assertLessEqual(p6_action_relative, 1.0e-6)
            self.assertLessEqual(a6_action_relative, 1.0e-6)
            self.assertLessEqual(p4_solution_relative, 1.0e-6)
            self.assertLessEqual(p4_matrix_relative["nonzero_complex_action"], 1.0e-6)
            for case in cases.values():
                self.assertEqual(
                    case["p6_system"].build_audit["owned_cell_count_global"], 105
                )

            report = {
                "schema": "task39extra.v5.5nm.rounded12.tensor-representative.105cell.v1",
                "status": "REAL_FE_MPC_TENSOR_CANDIDATE_COMPONENT_PASS",
                "scope": "105-cell coarsened-axis 5nm Si FE/MPC component; four actual zero-order ports, not full 600-channel run or resource qualification",
                "input_sha256": specification.input_sha256,
                "physical_model_sha256": specification.physical_model_sha256,
                "source_profile": cfg.case_name,
                "cell_count": cell_count,
                "material_n": [float(cfg.grating_index.real), float(cfg.grating_index.imag)],
                "full_mode_count": len(full_modes),
                "full_mode_sha256": full_mode_sha,
                "component_mode_count": len(zero_modes),
                "component_mode_sha256": mode_sha,
                "raw_geometry_class_count_per_degree": raw_class_count,
                "candidate_tensor_group_count_per_degree": tensor_group_count,
                "candidate_tensor_group_approximation": True,
                "candidate_schur_lu_recovery_key": "raw_float64_widths_plus_orientation",
                "oriented_schur_class_count_sum": expected_oriented_classes,
                "tensor_kernel_build_seconds": {
                    policy: {
                        "p6": float(case["p6_system"].build_audit["kernel_seconds_max"]),
                        "p4": float(case["p4_system"].build_audit["kernel_seconds_max"]),
                        "p6_total_builder_wall": float(case["p6_wall_seconds"]),
                        "p4_total_builder_wall": float(case["p4_wall_seconds"]),
                    }
                    for policy, case in cases.items()
                },
                "tensor_validation_retabulation_seconds": tensor_validation_seconds,
                "representative_tensor_comparison": tensor_comparisons,
                "representative_coordinate_hashes": representatives,
                "raw_vs_candidate": {
                    "p6_condensed_action_relative_difference": p6_action_relative,
                    "independent_original_A6_residual_action_relative_difference": a6_action_relative,
                    "original_A6_calls": native_a6_calls,
                    "A6_setup_identity_relative": {
                        policy: float(facts["native_identity_relative"])
                        for policy, facts in p6_native_facts.items()
                    },
                    "Schur_port_identity_relative": {
                        policy: float(facts["schur_port_identity_relative"])
                        for policy, facts in p6_native_facts.items()
                    },
                    "nonzero_internal_rhs_norm": float(np.linalg.norm(p6_rhs[interior])),
                    "explicit_nonzero_port_rhs_norm": float(np.linalg.norm(explicit_port_rhs)),
                    "p4_matrix_nonzero_complex_action_relative_difference": p4_matrix_relative["nonzero_complex_action"],
                    "p4_returned_solution_relative_difference": p4_solution_relative,
                    "p4_original_A4_returned_residual": p4_residuals,
                    "p4_explicit_port_rhs_augmented_matrix_residual": p4_augmented_port_residuals,
                    "p4_internal_rhs_norm": p4_rhs_norms,
                    "native_Aq_volume_projection_relative": aq_volume_relative,
                    "native_Aq_DtN_projection_relative": aq_dtn_relative,
                    "native_Aq_projection_passed": bool(aq["passed"]),
                    "p4_rhs_port_coupling_policy": "actual carrier terms; explicit complex port RHS separately solved against augmented matrix",
                },
                "gates": {
                    "raw_candidate_A6_action_limit": 1.0e-6,
                    "raw_candidate_p4_solution_limit": 1.0e-6,
                    "original_A4_return_limit": 1.0e-10,
                    "native_Aq_component_limit": 1.0e-10,
                    "all_p4_gates_passed": all(value <= 1.0e-10 for value in p4_residuals.values()),
                },
            }
            print("V5_5NM_GEOMETRY_105_FE_PROBE " + json.dumps(report, sort_keys=True), flush=True)
        finally:
            for value in reversed(owned_vectors):
                value.destroy()
            for inverse in reversed(inverses):
                inverse.destroy()
            for policy, case in list(cases.items()):
                action = case.get("p6_action")
                if action is not None:
                    action.destroy()
                    case["p6_action"] = None
                p4_system = case.get("p4_system")
                if p4_system is not None:
                    p4_system.destroy()
                    case["p4_system"] = None
            if owner is not None:
                owner.destroy()
            if local_transfer is not None:
                destroy = getattr(local_transfer, "destroy", None)
                if callable(destroy):
                    destroy()
            for bundle in (coarse, fine):
                if bundle is not None:
                    destroy_same_mesh_physical_action(bundle)
            levels.clear()
