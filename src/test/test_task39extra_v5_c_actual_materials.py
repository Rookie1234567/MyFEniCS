"""V5 C-stage small FE checks with the three authoritative Si input materials."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from dolfinx import fem
from mpi4py import MPI

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.runners.physical_intermediate import WorkflowLedger
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
    _build_same_mesh_levels,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    _build_split_volume_action,
)
from src.solvers.physical_equivalent_fast import build_packed_physical_action

ROOT = Path(__file__).resolve().parents[2]


def _parse_cpu_list(value: str) -> set[int]:
    cpus: set[int] = set()
    for item in value.split(","):
        bounds = item.split("-", 1)
        start = int(bounds[0])
        stop = int(bounds[-1])
        cpus.update(range(start, stop + 1))
    return cpus


MATERIAL_INPUTS = (
    (
        "13.5nm",
        (
            "input/task39extra_para_workstation_capacity/"
            "v5_node1_13p5nm_p6h7p5_q4.dat"
        ),
        0.999002304859 + 0.00182649365j,
    ),
    (
        "5nm",
        (
            "input/task39extra_para_workstation_capacity/"
            "original_5nm_si_p6h4_native.dat"
        ),
        0.99396854453 + 0.00435380777j,
    ),
    (
        "2nm",
        (
            "input/task39extra_para_workstation_capacity/"
            "original_2nm_si_p6h1p5_native.dat"
        ),
        0.99880148307 + 0.000213688647j,
    ),
)


class _BorrowedZeroDtN:
    """Volume-only material check; the separate 990 case checks real DtN."""

    def apply(self, _source, target):
        target.set(0.0)

    def destroy(self):
        pass


@unittest.skipUnless(
    os.environ.get("TASK39EXTRA_RUN_V5_MATERIAL_C") == "1"
    and os.environ.get("TASK39EXTRA_PORD64_ROOT"),
    "requires explicit task-local PORD64 activation",
)
class Task39ExtraV5ActualMaterialTests(unittest.TestCase):
    def test_three_authoritative_materials_native_vs_sumfactorized_p6_volume(self):
        rows = []
        for label, relative_input, expected_index in MATERIAL_INPUTS:
            specification = load_and_resolve(ROOT / relative_input)
            cfg = simulation_config_3d_from_normalized(
                specification.as_jsonable()
            )
            self.assertEqual(cfg.substrate_index, expected_index)
            self.assertEqual(cfg.grating_index, expected_index)

            # Keep the real geometry/material/phase identity, but use one
            # bounded, plane-aligned FE fixture rather than a full wavelength mesh.
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
            levels = _build_same_mesh_levels(
                small_cfg,
                MPI.COMM_SELF,
                (6,),
                include_positive_coefficients=False,
            )
            native_volume = fast = source = native_result = fast_result = None
            space = floquet = zero_dtn = None
            try:
                space = levels["spaces"][6]
                floquet = levels["floquets"][6]
                native_volume = _build_split_volume_action(
                    levels["mesh_data"],
                    small_cfg,
                    space,
                    floquet,
                    jit_options={},
                )
                zero_dtn = _BorrowedZeroDtN()
                fast = build_packed_physical_action(
                    {
                        "levels": levels,
                        "fine": {
                            "volume_action": native_volume,
                            "dtn_action": zero_dtn,
                        },
                    },
                    small_cfg,
                    contiguous_work=True,
                    preallocated_work=False,
                    sum_factorized_work=True,
                )
                if label == "13.5nm":
                    # Exercise the exact production marker path with actual
                    # packed-action facts, which may contain nested read-only
                    # mapping proxies from the immutable audit APIs.
                    with tempfile.TemporaryDirectory(
                        prefix="task39extra-v5-fast-action-ledger-"
                    ) as ledger_directory:
                        ledger_path = Path(ledger_directory)
                        ledger = WorkflowLedger(
                            ledger_path, ledger_path / "workflow_phase.json"
                        )
                        ledger.marker(
                            "retained_sum_factorized_physical_action_complete",
                            fast["facts"],
                        )
                        facts_record = json.loads(
                            (ledger_path / "workflow_phase.json").read_text()
                        )
                        self.assertEqual(
                            facts_record["stage"],
                            "retained_sum_factorized_physical_action_complete",
                        )
                        self.assertEqual(
                            facts_record["facts"]["schema"], fast["facts"]["schema"]
                        )

                source = fem.Function(space)
                source.interpolate(
                    lambda x: np.vstack(
                        (
                            x[0] + 1j * (1.0 + x[1]),
                            2.0 * x[1] + 1j * (2.0 + x[2]),
                            -x[2] + 1j * (3.0 + x[0]),
                        )
                    )
                )
                floquet.mpc.homogenize(source)
                source.x.scatter_forward()
                floquet.mpc.backsubstitution(source)
                source.x.scatter_forward()
                input_before = np.asarray(source.x.array).copy()

                native_result = native_volume.apply(source.x.petsc_vec).copy()
                fast_result = fast["volume_action"].apply(
                    source.x.petsc_vec
                ).copy()
                difference = native_result.copy()
                difference.axpy(-1.0, fast_result)
                relative = float(
                    difference.norm()
                    / max(native_result.norm(), np.finfo(np.float64).tiny)
                )
                difference.destroy()
                self.assertTrue(np.array_equal(input_before, source.x.array))
                self.assertLessEqual(relative, 1.0e-10)
                self.assertTrue(fast["facts"]["sum_factorized_work"])
                self.assertEqual(
                    len(fast["facts"]["kernels"]), 2
                )
                self.assertTrue(
                    all(
                        facts["sum_factorized_opt_in"]
                        for facts in fast["facts"]["kernels"]
                    )
                )
                rows.append(
                    {
                        "wavelength": label,
                        "input_sha256": specification.input_sha256,
                        "physical_model_sha256": specification.physical_model_sha256,
                        "material_n": [expected_index.real, expected_index.imag],
                        "material_epsilon": [
                            (expected_index**2).real,
                            (expected_index**2).imag,
                        ],
                        "cells": 5 * 3 * 7,
                        "rows_p6": int(space.dofmap.index_map.size_global),
                        "native_backend": "FFCx split physical volume action",
                        "candidate_backend": "sum-factorized p6 curl+mass kernels",
                        "relative_action_difference": relative,
                        "dtn_included": False,
                        "scope": "actual input material/phase on bounded FE geometry; not full wavelength mesh",
                    }
                )
                print(
                    "V5_ACTUAL_MATERIAL_VOLUME_PASS "
                    + json.dumps(rows[-1], sort_keys=True),
                    flush=True,
                )
            finally:
                if fast is not None:
                    fast["physical_action"].destroy()
                    fast = None
                if native_result is not None:
                    native_result.destroy()
                if fast_result is not None:
                    fast_result.destroy()
                if native_volume is not None:
                    native_volume.destroy()
                del levels, source, space, floquet, zero_dtn

        self.assertEqual([row["wavelength"] for row in rows], [
            "13.5nm", "5nm", "2nm"
        ])

    def test_actual_material_zero_order_aq_and_p4_inverse_components(self):
        from petsc4py import PETSc

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
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            build_same_mesh_physical_action,
            destroy_same_mesh_physical_action,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
            build_same_mesh_hcurl_owner_transfer,
        )
        from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
        from src.solvers.hcurl_assembly_time_condensation import (
            build_unconstrained_assembly_time_condensation,
        )
        from src.solvers.p4_cell_condensed_inverse import (
            P4CellCondensedInverse,
            P4RefinementLedger,
            assemble_condensed_ports,
        )
        cases = (
            ("13.5nm-q3", MATERIAL_INPUTS[0][1], 80, 3),
            (
                "13.5nm-q4",
                (
                    "input/task39extra_para_workstation_capacity/"
                    "v5_node1_13p5nm_p6h7p5_q4.dat"
                ),
                80,
                4,
            ),
            ("5nm-q4", MATERIAL_INPUTS[1][1], 600, 4),
            ("2nm-q4", MATERIAL_INPUTS[2][1], 3904, 4),
        )
        for label, relative_input, expected_modes, coarse_degree in cases:
            specification = load_and_resolve(ROOT / relative_input)
            cfg = simulation_config_3d_from_normalized(
                specification.as_jsonable()
            )
            small_cfg = replace(
                cfg,
                mesh_axis_cell_counts=(3, 2, 3),
                mesh_axis_x_values=None,
                mesh_axis_y_values=None,
                mesh_axis_z_values=None,
                mesh_axis_z_profile=None,
                mesh_plan_id=None,
                mesh_plan_sha256=None,
            )
            levels = _build_same_mesh_levels(
                small_cfg,
                MPI.COMM_SELF,
                (6, coarse_degree),
                include_positive_coefficients=False,
            )
            fine = coarse = owner = local_transfer = p4_system = None
            factor = inverse = ledger = None
            rhs = solution = reduced_rhs = None
            try:
                full_modes, _full_rows, full_mode_sha = build_dynamic_mode_inventory(
                    small_cfg
                )
                self.assertEqual(len(full_modes), expected_modes)
                port_modes = tuple(
                    mode for mode in full_modes if mode.m == 0 and mode.n == 0
                )
                self.assertEqual(len(port_modes), 4)
                self.assertEqual(
                    {(mode.side, mode.polarization) for mode in port_modes},
                    {
                        ("top", "s"),
                        ("top", "p"),
                        ("bottom", "s"),
                        ("bottom", "p"),
                    },
                )
                port_rows, _encoded, port_mode_sha = build_ordered_mode_manifest(
                    port_modes, small_cfg
                )
                selected_modes = (port_modes, port_rows, port_mode_sha)
                fine = build_same_mesh_physical_action(
                    levels, small_cfg, 6, mode_inventory=selected_modes
                )
                coarse = build_same_mesh_physical_action(
                    levels,
                    small_cfg,
                    coarse_degree,
                    mode_inventory=selected_modes,
                )
                local_transfer = build_same_mesh_hcurl_transfer(
                    6, coarse_degree
                )
                owner = build_same_mesh_hcurl_owner_transfer(
                    levels["spaces"][6],
                    levels["floquets"][6],
                    levels["spaces"][coarse_degree],
                    levels["floquets"][coarse_degree],
                    local_transfer=local_transfer,
                    fixed_serial_owner_route=True,
                    optimized_owner_apply=True,
                )
                aq_runtime = SimpleNamespace(
                    levels=levels,
                    coarse_degree=coarse_degree,
                    transfer=AlgebraicOwnerTransfer(owner),
                    fine=fine,
                    p4=coarse,
                )
                aq = _native_aq_projection_check(aq_runtime)
                self.assertTrue(aq["passed"])
                self.assertLessEqual(
                    aq["native_Aq_volume_vs_PqH_A6_volume_P"]["relative"],
                    1.0e-10,
                )
                self.assertLessEqual(
                    aq["native_Aq_DtN_vs_PqH_A6_DtN_P"]["relative"],
                    1.0e-10,
                )

                carrier = coarse["dtn_action"].carrier
                compiled = _compile_volume_form(coarse["volume_action"])
                groups, group_by_row = _support_groups(
                    levels["spaces"][coarse_degree], carrier
                )
                p4_system = build_unconstrained_assembly_time_condensation(
                    compiled,
                    levels["spaces"][coarse_degree],
                    levels["mesh_data"].cell_tags,
                    mpc=levels["floquets"][coarse_degree].mpc,
                    appended_global_rows=len(carrier.entries),
                    appended_support_owned_cell_groups=groups,
                    appended_support_group_by_row=group_by_row,
                    dense_appended_block=True,
                    sum_duplicate_cell_integrals=True,
                    strict_local_checks=True,
                    defer_final_assembly=True,
                    geometry_identity_policy="raw_unrounded",
                    share_identity_cache=True,
                )
                port_terms = assemble_condensed_ports(p4_system, carrier)
                p4_system.matrix.assemble()

                PETSc.Options()["mat_mumps_icntl_7"] = 4
                factor = _MumpsFactor(p4_system.matrix)
                factor.set_icntl(23, 0)
                factor.symbolic(p4_system.matrix)
                factor.numeric(p4_system.matrix)
                self.assertEqual(factor.get_icntl(23), 0)
                self.assertEqual(int(factor.info((1, 7))["infog"]["1"]), 0)
                self.assertEqual(int(factor.info((7,))["infog"]["7"]), 4)
                inverse = P4CellCondensedInverse(
                    p4_system,
                    factor,
                    port_terms=port_terms,
                    owns_condensed=True,
                    owns_factor=True,
                    retain_through_postprocess_v18=False,
                )
                factor = None
                proxy = SimpleNamespace(
                    p4=coarse,
                    p4_system=p4_system,
                )
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

                full_rows = int(p4_system.full_rows)
                interior_dofs = np.unique(
                    np.concatenate(
                        [
                            cell.interior_original_dofs
                            for cell in p4_system.cell_recovery_maps
                        ]
                    )
                )
                rhs = PETSc.Vec().createMPI(
                    (full_rows, full_rows), comm=MPI.COMM_SELF
                )
                index = interior_dofs.astype(np.float64) + 1.0
                rhs.getArray()[interior_dofs] = (
                    np.sin(0.071 * index) + 1j * np.cos(0.043 * index)
                )
                rhs.assemble()
                interior_rhs_norm = float(
                    np.linalg.norm(rhs.getValues(interior_dofs))
                )
                self.assertGreater(interior_rhs_norm, 0.0)
                slaves = np.asarray(
                    levels["floquets"][coarse_degree].mpc.slaves,
                    dtype=np.int64,
                )
                if len(slaves):
                    self.assertEqual(
                        float(np.max(np.abs(rhs.getValues(slaves)))), 0.0
                    )
                reduced_rhs = inverse._reduce_storage_rhs(rhs)
                try:
                    port_rhs_norm = float(
                        np.linalg.norm(
                            np.asarray(reduced_rhs.getArray(readonly=True))[
                                p4_system.active_rows :
                            ]
                        )
                    )
                finally:
                    reduced_rhs.destroy()
                    reduced_rhs = None
                di_norm = float(
                    sum(np.linalg.norm(term.Di) for term in port_terms.values())
                )
                nonzero_di_cells = sum(
                    bool(np.any(term.Di)) for term in port_terms.values()
                )
                port_rhs_relative_to_interior = port_rhs_norm / max(
                    interior_rhs_norm, np.finfo(np.float64).tiny
                )
                roundoff_relative = 128.0 * np.finfo(np.float64).eps
                if di_norm == 0.0:
                    self.assertEqual(port_rhs_norm, 0.0)
                    port_rhs_scope = "structurally_zero_Di"
                elif port_rhs_relative_to_interior <= roundoff_relative:
                    port_rhs_scope = "roundoff_level_not_counted_as_nonzero"
                else:
                    port_rhs_scope = "nonzero_interior_induced_Di_RHS"

                solution = ledger.solve(rhs)
                self.assertEqual(ledger.last_audit["status"], "P4_RETURN_PASS")
                self.assertLessEqual(
                    ledger.last_audit["refinement_count"], 2
                )
                self.assertLessEqual(
                    ledger.last_audit["rows"][-1]["relative_residual"],
                    1.0e-10,
                )
                self.assertEqual(
                    ledger.last_audit["rows"][-1]["port_closure"]["status"],
                    "PASS",
                )
                self.assertGreater(
                    ledger.last_audit["port_state"]["norm"], 0.0
                )
                self.assertEqual(ledger.last_audit["factor_counts"]["symbolic_calls"], 1)
                self.assertEqual(ledger.last_audit["factor_counts"]["numeric_calls"], 1)
                self.assertLessEqual(ledger.last_audit["factor_counts"]["solve_calls"], 3)

                record = {
                    "case": label,
                    "input_sha256": specification.input_sha256,
                    "physical_model_sha256": specification.physical_model_sha256,
                    "wavelength_nm": float(cfg.lambda0),
                    "material_n": [
                        float(cfg.grating_index.real),
                        float(cfg.grating_index.imag),
                    ],
                    "full_mode_count": len(full_modes),
                    "full_mode_sha256": full_mode_sha,
                    "small_component_mode_count": len(port_modes),
                    "small_component_mode_sha256": port_mode_sha,
                    "small_component_mode_orders": [
                        [mode.side, mode.m, mode.n, mode.polarization]
                        for mode in port_modes
                    ],
                    "cells": 3 * 2 * 3,
                    "coarse_degree": coarse_degree,
                    "aq_volume_relative": aq[
                        "native_Aq_volume_vs_PqH_A6_volume_P"
                    ]["relative"],
                    "aq_dtn_relative": aq[
                        "native_Aq_DtN_vs_PqH_A6_DtN_P"
                    ]["relative"],
                    "p4_rows": int(p4_system.matrix.getSize()[0]),
                    "p4_nnz": int(p4_system.matrix.getInfo()["nz_used"]),
                    "interior_rhs_norm": interior_rhs_norm,
                    "reduced_port_rhs_norm": port_rhs_norm,
                    "port_rhs_relative_to_interior_rhs": port_rhs_relative_to_interior,
                    "roundoff_relative_reference": roundoff_relative,
                    "port_Di_frobenius_sum": di_norm,
                    "nonzero_Di_cells": nonzero_di_cells,
                    "port_rhs_scope": port_rhs_scope,
                    "recovered_port_state_norm": ledger.last_audit["port_state"][
                        "norm"
                    ],
                    "p4_true_relative_residual": ledger.last_audit["rows"][-1][
                        "relative_residual"
                    ],
                    "p4_refinements": ledger.last_audit["refinement_count"],
                    "p4_factor_calls": ledger.last_audit["factor_counts"],
                    "rhs_source": "deterministic nonzero cell-interior FE forcing",
                    "scope": (
                        "small FE component with this input's actual material, Floquet phase, "
                        "and selected actual zero-order ports; not full-channel qualification"
                    ),
                }
                print(
                    "V5_ACTUAL_MATERIAL_AQ_P4_PASS "
                    + json.dumps(record, sort_keys=True),
                    flush=True,
                )
            finally:
                if solution is not None:
                    solution.destroy()
                if ledger is not None:
                    ledger.last_audit.clear()
                if inverse is not None:
                    inverse.destroy()
                    p4_system = None
                elif factor is not None:
                    factor.destroy()
                if p4_system is not None:
                    p4_system.destroy()
                for bundle in (coarse, fine):
                    if bundle is not None:
                        destroy_same_mesh_physical_action(bundle)
                if owner is not None:
                    owner.destroy()
                if rhs is not None:
                    rhs.destroy()
                try:
                    del PETSc.Options()["mat_mumps_icntl_7"]
                except KeyError:
                    pass
                levels.clear()

    def test_small_real_h6_native_fast_window_and_apply(self):
        from src.solvers.fullspace_lor_edge_geometric_mg_global import POWER_STEPS
        from src.solvers.fullspace_lor_native_hx_fixture import (
            build_frozen_fullspace_primal_source,
        )
        from src.solvers.physical_light_setup import build_light_h6_setup

        specification = load_and_resolve(
            ROOT
            / "input/task39extra_para_workstation_capacity/"
            "v5_node1_13p5nm_p6h7p5_q4.dat"
        )
        cfg = simulation_config_3d_from_normalized(
            specification.as_jsonable()
        )
        small_cfg = replace(
            cfg,
            mesh_axis_cell_counts=(3, 2, 3),
            mesh_axis_x_values=None,
            mesh_axis_y_values=None,
            mesh_axis_z_values=None,
            mesh_axis_z_profile=None,
            mesh_plan_id=None,
            mesh_plan_sha256=None,
        )
        levels = None
        native_h6 = fast_h6 = seed = native_output = fast_output = None
        try:
            levels = _build_same_mesh_levels(
                small_cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=True
            )
            marker = lambda *_args, **_kwargs: None
            native_h6 = build_light_h6_setup(
                levels,
                small_cfg,
                marker,
                packed_power10=False,
                packed_apply=False,
            )
            fast_h6 = build_light_h6_setup(
                levels,
                small_cfg,
                marker,
                packed_power10=True,
                packed_apply=True,
                sum_factorized_work=True,
                sum_factorized_power10=True,
            )
            seed, _seed_facts = build_frozen_fullspace_primal_source(
                levels["spaces"][6], levels["floquets"][6], small_cfg, "gradient"
            )
            gradient_seed_sha = hashlib.sha256(seed.array.tobytes()).hexdigest()
            before = np.asarray(seed.array, dtype=np.complex128).copy()

            native_diag = np.asarray(
                native_h6["p6_shell"].diagonal.array, dtype=np.complex128
            ).copy()
            fast_diag = np.asarray(
                fast_h6["p6_shell"].diagonal.array, dtype=np.complex128
            ).copy()
            diagonal_relative = float(
                np.linalg.norm(native_diag - fast_diag)
                / max(np.linalg.norm(native_diag), np.finfo(np.float64).tiny)
            )

            # These are B6 positive-form actions, not the H6 smoother.
            native_b6 = np.asarray(
                native_h6["p6_shell"].action.apply(seed).array,
                dtype=np.complex128,
            ).copy()
            fast_b6 = np.asarray(
                fast_h6["p6_shell"].action.apply(seed).array,
                dtype=np.complex128,
            ).copy()
            b6_relative = float(
                np.linalg.norm(native_b6 - fast_b6)
                / max(np.linalg.norm(native_b6), np.finfo(np.float64).tiny)
            )

            native_output = native_h6["h6"].apply(seed)
            native_h6_values = np.asarray(
                native_output.array, dtype=np.complex128
            ).copy()
            native_output.destroy()
            native_output = None
            fast_output = fast_h6["h6"].apply(seed)
            fast_h6_values = np.asarray(
                fast_output.array, dtype=np.complex128
            ).copy()
            fast_output.destroy()
            fast_output = None
            h6_relative = float(
                np.linalg.norm(native_h6_values - fast_h6_values)
                / max(
                    np.linalg.norm(native_h6_values),
                    np.finfo(np.float64).tiny,
                )
            )

            native_power = np.asarray(
                native_h6["h6"].power_history, dtype=np.float64
            )
            fast_power = np.asarray(
                fast_h6["h6"].power_history, dtype=np.float64
            )
            power_history_relative = float(
                np.linalg.norm(native_power - fast_power)
                / max(np.linalg.norm(native_power), np.finfo(np.float64).tiny)
            )
            lambda_power10_relative = float(
                abs(
                    native_h6["h6"].lambda_power10
                    - fast_h6["h6"].lambda_power10
                )
                / max(
                    abs(native_h6["h6"].lambda_power10),
                    np.finfo(np.float64).tiny,
                )
            )
            lambda_hi_relative = float(
                abs(native_h6["h6"].lambda_hi - fast_h6["h6"].lambda_hi)
                / max(
                    abs(native_h6["h6"].lambda_hi),
                    np.finfo(np.float64).tiny,
                )
            )
            lambda_lo_relative = float(
                abs(native_h6["h6"].lambda_lo - fast_h6["h6"].lambda_lo)
                / max(
                    abs(native_h6["h6"].lambda_lo),
                    np.finfo(np.float64).tiny,
                )
            )
            self.assertEqual(
                native_h6["light_facts"]["seed_sha256"],
                fast_h6["light_facts"]["seed_sha256"],
            )
            self.assertEqual(len(native_power), POWER_STEPS)
            self.assertEqual(len(fast_power), POWER_STEPS)
            self.assertTrue(np.all(np.isfinite(native_power)))
            self.assertTrue(np.all(np.isfinite(fast_power)))
            self.assertEqual(
                native_h6["h6"].power_matrix_mult_count, 2 * POWER_STEPS
            )
            self.assertEqual(
                fast_h6["h6"].power_matrix_mult_count, 2 * POWER_STEPS
            )
            self.assertEqual(
                native_h6["h6"].lambda_hi,
                1.10 * native_h6["h6"].lambda_power10,
            )
            self.assertEqual(
                fast_h6["h6"].lambda_hi,
                1.10 * fast_h6["h6"].lambda_power10,
            )
            self.assertEqual(
                native_h6["h6"].lambda_lo, 0.10 * native_h6["h6"].lambda_hi
            )
            self.assertEqual(
                fast_h6["h6"].lambda_lo, 0.10 * fast_h6["h6"].lambda_hi
            )
            for relative in (
                diagonal_relative,
                b6_relative,
                h6_relative,
                power_history_relative,
                lambda_power10_relative,
                lambda_hi_relative,
                lambda_lo_relative,
            ):
                self.assertTrue(np.isfinite(relative))
                self.assertLessEqual(relative, 1.0e-10)
            np.testing.assert_array_equal(seed.array, before)
            record = {
                "schema_version": "task039extra.v5.small-h6-native-fast.v1",
                "scope": "18-cell real FE H6 component; not a 990-cell timing or full-run qualification",
                "input_sha256": specification.input_sha256,
                "physical_model_sha256": specification.physical_model_sha256,
                "mesh_cells": 18,
                "power_seed_sha256": native_h6["light_facts"]["seed_sha256"],
                "gradient_vector_sha256": gradient_seed_sha,
                "native_backend": native_h6["light_facts"]["kernel"]["backend"],
                "fast_backend": fast_h6["light_facts"]["kernel"]["backend"],
                "positive_B6_action_relative": b6_relative,
                "actual_H6_smoother_apply_relative": h6_relative,
                "diagonal_relative": diagonal_relative,
                "power_history_relative": power_history_relative,
                "lambda_power10_relative": lambda_power10_relative,
                "lambda_hi_relative": lambda_hi_relative,
                "lambda_lo_relative": lambda_lo_relative,
                "native_power_matrix_mult_count": native_h6["h6"].power_matrix_mult_count,
                "fast_power_matrix_mult_count": fast_h6["h6"].power_matrix_mult_count,
                "relative_tolerance": 1.0e-10,
                "borrowed_B6_vectors_destroyed": False,
                "owned_H6_outputs_destroyed": True,
            }
            print("V5_SMALL_H6_NATIVE_FAST_PASS " + json.dumps(record, sort_keys=True), flush=True)
        finally:
            if native_output is not None:
                native_output.destroy()
            if fast_output is not None:
                fast_output.destroy()
            if seed is not None:
                seed.destroy()
            for setup in (native_h6, fast_h6):
                if setup is not None:
                    setup["h6"].destroy()
                    setup["p6_shell"].destroy()
            if levels is not None:
                levels.clear()

    def test_r13_990_q3_q4_native_aq_projection(self):
        from src.runners.physical_retained_condensed_v20 import (
            _native_aq_projection_check,
        )
        from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
        from src.solvers.fullspace_physical_intermediate_runtime import (
            AlgebraicOwnerTransfer,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg import (
            build_same_mesh_hcurl_transfer,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            build_same_mesh_physical_action,
            destroy_same_mesh_physical_action,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
            build_same_mesh_hcurl_owner_transfer,
        )

        q3_spec = load_and_resolve(
            ROOT
            / "input/task39extra_para_workstation_capacity/"
            "v5_node1_13p5nm_p6h7p5_q3.dat"
        )
        q4_spec = load_and_resolve(
            ROOT
            / "input/task39extra_para_workstation_capacity/"
            "v5_node1_13p5nm_p6h7p5_q4.dat"
        )
        cfg_by_degree = {
            3: simulation_config_3d_from_normalized(q3_spec.as_jsonable()),
            4: simulation_config_3d_from_normalized(q4_spec.as_jsonable()),
        }
        cfg = cfg_by_degree[4]
        self.assertEqual(q3_spec.physical_model_sha256, q4_spec.physical_model_sha256)
        self.assertEqual(tuple(cfg_by_degree[3].mesh_axis_cell_counts), (9, 5, 22))
        self.assertEqual(tuple(cfg.mesh_axis_cell_counts), (9, 5, 22))
        self.assertEqual(cfg_by_degree[3].mesh_plan_sha256, cfg.mesh_plan_sha256)
        for name in (
            "mesh_axis_x_values",
            "mesh_axis_y_values",
            "mesh_axis_z_values",
        ):
            self.assertTrue(
                np.array_equal(
                    getattr(cfg_by_degree[3], name), getattr(cfg, name)
                ),
                name,
            )

        levels = None
        fine = None
        q_actions = {}
        owners = {}
        try:
            levels = _build_same_mesh_levels(
                cfg,
                MPI.COMM_SELF,
                (6, 3, 4),
                include_positive_coefficients=True,
            )
            mesh_cells = int(
                levels["mesh"].topology.index_map(
                    levels["mesh"].topology.dim
                ).size_global
            )
            self.assertEqual(mesh_cells, 990)
            mode_facts = {}
            for degree, case_cfg in cfg_by_degree.items():
                modes, mode_rows, mode_sha = build_dynamic_mode_inventory(case_cfg)
                self.assertEqual(len(modes), 80)
                mode_facts[degree] = (modes, mode_rows, mode_sha)
            self.assertEqual(mode_facts[3][2], mode_facts[4][2])
            fine = build_same_mesh_physical_action(
                levels, cfg, 6, mode_inventory=mode_facts[4]
            )

            aq_rows = []
            for degree in (3, 4):
                case_cfg = cfg_by_degree[degree]
                coarse = build_same_mesh_physical_action(
                    levels, case_cfg, degree, mode_inventory=mode_facts[degree]
                )
                q_actions[degree] = coarse
                local_transfer = build_same_mesh_hcurl_transfer(6, degree)
                owner = build_same_mesh_hcurl_owner_transfer(
                    levels["spaces"][6],
                    levels["floquets"][6],
                    levels["spaces"][degree],
                    levels["floquets"][degree],
                    local_transfer=local_transfer,
                    fixed_serial_owner_route=True,
                    optimized_owner_apply=True,
                )
                owners[degree] = owner
                adapter = AlgebraicOwnerTransfer(owner)
                aq_runtime = SimpleNamespace(
                    levels=levels,
                    coarse_degree=degree,
                    transfer=adapter,
                    fine=fine,
                    p4=coarse,
                )
                facts = _native_aq_projection_check(aq_runtime)
                self.assertTrue(facts["passed"])
                volume_relative = float(
                    facts["native_Aq_volume_vs_PqH_A6_volume_P"]["relative"]
                )
                dtn_relative = float(
                    facts["native_Aq_DtN_vs_PqH_A6_DtN_P"]["relative"]
                )
                self.assertLessEqual(volume_relative, 1.0e-10)
                self.assertLessEqual(dtn_relative, 1.0e-10)
                aq_rows.append(
                    {
                        "coarse_degree": degree,
                        "coarse_global_rows": int(
                            levels["spaces"][degree].dofmap.index_map.size_global
                        ),
                        "mode_count": len(mode_facts[degree][0]),
                        "mode_sha256": mode_facts[degree][2],
                        "volume_relative": volume_relative,
                        "dtn_relative": dtn_relative,
                        "owner_primal_calls": int(adapter.primal_count),
                        "owner_adjoint_calls": int(adapter.adjoint_count),
                    }
                )
            record = {
                "schema_version": "task039extra.v5.r13-990-aq-projection.v1",
                "scope": "990-cell 13.5nm q3/q4 Aq component; no global coarse factor or formal solve",
                "q3_input_sha256": q3_spec.input_sha256,
                "q4_input_sha256": q4_spec.input_sha256,
                "physical_model_sha256": q4_spec.physical_model_sha256,
                "mesh_plan_sha256": cfg.mesh_plan_sha256,
                "mesh_cells": mesh_cells,
                "channel_count": len(mode_facts[4][0]),
                "mode_sha256": mode_facts[4][2],
                "coarse_projections": aq_rows,
                "tolerance": 1.0e-10,
            }
            print("V5_R13_990_AQ_PROJECTION_PASS " + json.dumps(record, sort_keys=True), flush=True)
        finally:
            for owner in owners.values():
                owner.destroy()
            for bundle in q_actions.values():
                destroy_same_mesh_physical_action(bundle)
            if fine is not None:
                destroy_same_mesh_physical_action(fine)
            if levels is not None:
                levels.clear()

    def test_r13_990_local_a6_h6_workload(self):
        from petsc4py import PETSc

        from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
        from src.solvers.fullspace_lor_native_hx_fixture import (
            build_frozen_fullspace_primal_source,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            build_same_mesh_physical_action,
            destroy_same_mesh_physical_action,
        )
        from src.solvers.physical_equivalent_fast import build_packed_physical_action
        from src.solvers.physical_light_setup import build_light_h6_setup

        side = os.environ.get("TASK39EXTRA_R13_CPU_SIDE")
        if side not in {"node0", "node1"}:
            self.skipTest("run in a separate CPU23/node0 or CPU24/node1 process")
        expected_cpu, expected_node = (23, 0) if side == "node0" else (24, 1)
        affinity = sorted(os.sched_getaffinity(0))
        self.assertEqual(affinity, [expected_cpu])
        status = Path("/proc/self/status").read_text()
        mems_line = next(
            line for line in status.splitlines() if line.startswith("Mems_allowed_list:")
        )
        allowed_nodes = _parse_cpu_list(mems_line.split(":", 1)[1].strip())
        self.assertIn(expected_node, allowed_nodes)

        maps_output = os.environ.get("TASK39EXTRA_R13_NUMA_MAPS_SNAPSHOT")
        self.assertTrue(maps_output, "provide a unique per-process numa_maps snapshot path")
        maps_path = Path(maps_output)
        self.assertFalse(maps_path.exists(), f"refusing to overwrite {maps_path}")

        specification = load_and_resolve(
            ROOT
            / "input/task39extra_para_workstation_capacity/"
            "v5_node1_13p5nm_p6h7p5_q4.dat"
        )
        cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
        levels = None
        fine = fast_a6 = h6_setup = seed = None
        native_a6_target = fast_a6_target = None
        try:
            levels = _build_same_mesh_levels(
                cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=True
            )
            cells = int(
                levels["mesh"].topology.index_map(
                    levels["mesh"].topology.dim
                ).size_global
            )
            self.assertEqual(cells, 990)
            modes, mode_rows, mode_sha = build_dynamic_mode_inventory(cfg)
            self.assertEqual(len(modes), 80)
            fine = build_same_mesh_physical_action(
                levels, cfg, 6, mode_inventory=(modes, mode_rows, mode_sha)
            )
            fast_a6 = build_packed_physical_action(
                {"levels": levels, "fine": fine},
                cfg,
                contiguous_work=True,
                preallocated_work=False,
                sum_factorized_work=True,
            )
            h6_setup = build_light_h6_setup(
                levels,
                cfg,
                lambda *_args, **_kwargs: None,
                packed_power10=True,
                packed_apply=True,
                sum_factorized_work=True,
                sum_factorized_power10=True,
            )
            seed, _seed_facts = build_frozen_fullspace_primal_source(
                levels["spaces"][6], levels["floquets"][6], cfg, "gradient"
            )
            seed_values = np.asarray(seed.array, dtype=np.complex128).copy()
            seed_sha = hashlib.sha256(seed_values.tobytes()).hexdigest()
            self.assertTrue(np.all(np.isfinite(seed_values)))

            full_rows = int(
                levels["spaces"][6].dofmap.index_map.size_global
                * levels["spaces"][6].dofmap.index_map_bs
            )
            native_a6_target = PETSc.Vec().createMPI(
                (full_rows, full_rows), comm=MPI.COMM_SELF
            )
            fast_a6_target = native_a6_target.duplicate()

            def apply_a6(action, target):
                action.apply(seed, target)
                return np.asarray(target.array, dtype=np.complex128).copy()

            native_a6_values = apply_a6(fine["physical_action"], native_a6_target)
            fast_a6_values = apply_a6(
                fast_a6["physical_action"], fast_a6_target
            )
            a6_relative = float(
                np.linalg.norm(native_a6_values - fast_a6_values)
                / max(
                    np.linalg.norm(native_a6_values),
                    np.finfo(np.float64).tiny,
                )
            )
            self.assertLessEqual(a6_relative, 1.0e-10)

            def apply_h6():
                output = h6_setup["h6"].apply(seed)
                try:
                    return np.asarray(output.array, dtype=np.complex128).copy()
                finally:
                    output.destroy()

            h6_reference = apply_h6()
            self.assertTrue(np.isfinite(np.linalg.norm(h6_reference)))

            def timed(label, apply):
                warm = apply()
                warm_norm = float(np.linalg.norm(warm))
                start_cpu = time.process_time()
                start_wall = time.perf_counter()
                norms = []
                for _ in range(3):
                    values = apply()
                    norms.append(float(np.linalg.norm(values)))
                wall = time.perf_counter() - start_wall
                cpu_seconds = time.process_time() - start_cpu
                self.assertTrue(np.all(np.isfinite(norms)))
                self.assertTrue(np.isfinite(warm_norm))
                return {
                    "operation": label,
                    "passes": 3,
                    "wall_seconds": wall,
                    "process_cpu_seconds": cpu_seconds,
                    "seconds_per_apply": wall / 3,
                    "warm_norm": warm_norm,
                    "timed_output_norms": norms,
                }

            raw_maps = Path("/proc/self/numa_maps").read_bytes()
            maps_path.write_bytes(raw_maps)
            numa_maps_sha = hashlib.sha256(raw_maps).hexdigest()
            anon_pages = {0: 0, 1: 0}
            node_pages = {0: 0, 1: 0}
            for line in raw_maps.decode("utf-8", errors="replace").splitlines():
                tokens = line.split()
                if any(token.startswith("anon=") for token in tokens):
                    for token in tokens:
                        if token.startswith("N0="):
                            anon_pages[0] += int(token[3:])
                        elif token.startswith("N1="):
                            anon_pages[1] += int(token[3:])
                for token in tokens:
                    if token.startswith("N0="):
                        node_pages[0] += int(token[3:])
                    elif token.startswith("N1="):
                        node_pages[1] += int(token[3:])
            self.assertGreater(anon_pages[expected_node], 0)
            other_node = 1 - expected_node
            total_anon_pages = sum(anon_pages.values())
            self.assertGreater(
                anon_pages[expected_node], anon_pages[other_node],
                "the majority of process anonymous pages must be on the bound local node",
            )

            timings = [
                timed(
                    "A6_native",
                    lambda: apply_a6(fine["physical_action"], native_a6_target),
                ),
                timed(
                    "A6_sumfactorized",
                    lambda: apply_a6(
                        fast_a6["physical_action"], fast_a6_target
                    ),
                ),
                timed("H6_sumfactorized_smoother", apply_h6),
            ]
            np.testing.assert_array_equal(seed.array, seed_values)
            record = {
                "schema_version": "task039extra.v5.r13-990-local-workload.v1",
                "scope": "single local NUMA process; timing is one side of a two-process pair, not an isolated-system claim",
                "side": side,
                "cpu": expected_cpu,
                "numa_node": expected_node,
                "affinity": affinity,
                "mems_allowed_list": mems_line.split(":", 1)[1].strip(),
                "input_sha256": specification.input_sha256,
                "physical_model_sha256": specification.physical_model_sha256,
                "mesh_cells": cells,
                "channel_count": len(modes),
                "mode_sha256": mode_sha,
                "vector_sha256": seed_sha,
                "a6_native_vs_sumfactorized_relative": a6_relative,
                "timings": timings,
                "numa_maps_snapshot": str(maps_path),
                "numa_maps_sha256": numa_maps_sha,
                "numa_maps_node_pages": node_pages,
                "numa_maps_anonymous_pages": anon_pages,
                "numa_maps_anonymous_local_fraction": (
                    anon_pages[expected_node] / total_anon_pages
                    if total_anon_pages
                    else None
                ),
                "target_node_anonymous_pages": anon_pages[expected_node],
            }
            print("V5_R13_990_LOCAL_WORKLOAD " + json.dumps(record, sort_keys=True), flush=True)
        finally:
            if native_a6_target is not None:
                native_a6_target.destroy()
            if fast_a6_target is not None:
                fast_a6_target.destroy()
            if seed is not None:
                seed.destroy()
            if h6_setup is not None:
                h6_setup["h6"].destroy()
                h6_setup["p6_shell"].destroy()
            if fast_a6 is not None:
                fast_a6["physical_action"].destroy()
                fast_a6.clear()
            if fine is not None:
                destroy_same_mesh_physical_action(fine)
            if levels is not None:
                levels.clear()
if __name__ == "__main__":
    unittest.main()
