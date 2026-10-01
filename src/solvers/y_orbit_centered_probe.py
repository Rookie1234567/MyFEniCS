"""Fresh full3D centered p2 dense authority, independent of condensation.

The original public full FFCx/MPC assembly and all port outer products are
reused. Global dense factors are sequentially released; this tiny authority
does not implement or qualify a target-scale dense solver.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from scipy.linalg import lu_factor, lu_solve

from .task40extra_y_orbit_reference import (
    LIMITS, SEED, FullOriginalAction, YReferenceInverse, assemble_original_dense,
    audit_port_aliases, build_y_orbit_layout, pilot_config, solve_notched_fgmres, _relative,
)
from .y_orbit_centered_evidence import (
    CENTERED_SCOPE, SOURCES, centered_identity, interior_only_rhs, original_packet,
    recovered_field_and_modes, save_mpc_inventory, fixture_interior_positions, require_output_packet,
)


def run_centered_dense_probe(input_path, *, event, save_array, allocation_gate, old_oracle,
                             live_component_oracle=False, live_component_record_path=None):
    from mpi4py import MPI
    from petsc4py import PETSc
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import (
        _build_split_volume_action, build_physical_rhs, build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )
    from .fullspace_physical_action import FullspacePhysicalAction
    from .y_orbit_condensed_adapter import _mpc_expansion_width
    from .y_orbit_sparse_reference import integer_admission
    from .y_orbit_sparse_probe import _check_packet, _notch_supported_rhs
    from src.geometry.mesh_builder_3d import _mark_cells, _rectangular_air_void_audit

    cfg, axes, input_sha = pilot_config(input_path, azimuth_deg=5.0)
    levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (2,), include_positive_coefficients=False)
    space, floquet = levels["spaces"][2], levels["floquets"][2]
    allocation_gate("full_Hcurl_orbit_map", {"matrix_payload_bytes": 4 << 20,
                     "workspace_bytes": 16 << 20, "small_p2_only": True})
    layout = build_y_orbit_layout(space, floquet, cfg, axes)
    if (len(layout.independent) != 2048 or layout.full_rows != 2394
            or int(levels["mesh"].topology.index_map(3).size_local) != 80):
        raise ValueError("centered dense authority requires the fixed actual 80-cell full3D p2 inventory")
    for name, matrix in (("Q", layout.q), ("R_inverse", layout.r_inverse), ("F", layout.fourier),
                         ("T", layout.native_translation)):
        for suffix in ("data", "indices", "indptr"):
            save_array(name+"_"+suffix, getattr(matrix, suffix))
    save_array("independent_storage_rows", layout.independent)
    base = action0 = action1 = notched = None
    try:
        base = build_same_mesh_physical_action(levels, cfg, 2, dtn_phase_gauge="boundary_plane")
        if live_component_oracle:
            from .y_orbit_live_boundary_contract import qualify_live_identity, require_live_carrier_unchanged
            if live_component_record_path is None: raise ValueError("same-live qualification receipt path is required")
            identity = qualify_live_identity(base,record_path=live_component_record_path,
                                             allocation_gate=allocation_gate,event=event)
            qualified_carrier = base["dtn_action"].carrier
        else:
            identity = centered_identity(base,event=event)
        save_mpc_inventory(base, layout, save_array)
        save_array("actual_interior_positions",fixture_interior_positions(space,layout))
        ports = audit_port_aliases(base["dtn_action"].carrier, layout, cfg, base["modes"])
        # Keep the historical RNG ordering: all real entries, then imaginary.
        rng = np.random.default_rng(SEED)
        generic = rng.standard_normal(2048) + 1j*rng.standard_normal(2048)
        excitation = np.asarray(layout.modal_norms(generic, dual=True))
        if np.min(excitation)/np.linalg.norm(excitation) < LIMITS["excitation"]:
            raise ValueError("generic full original dual load must excite all four q")
        rhs_storage, physical_facts = build_physical_rhs(base)
        try:
            physical = rhs_storage.getArray(readonly=True)[layout.independent].copy()
        finally:
            rhs_storage.destroy()
        scale = 7/135
        box = tuple(v*scale for v in (25, 33.5, 6.25, 18.75, 40, 80))
        notch_cfg = replace(cfg, case_name="y_orbit_p2_algebra_notch", air_void_box_nm=box,
                            geometry_identity=cfg.geometry_identity+".notch")
        tags = _mark_cells(levels["mesh"], notch_cfg)
        changed = np.flatnonzero(tags.values != levels["mesh_data"].cell_tags.values)
        if len(changed) != 2:
            raise ValueError("the unchanged mesh must retain its actual two-cell nonseparable notch")
        supported, support_facts = _notch_supported_rhs(space, layout, changed)
        sources = {"generic": generic, "interior_only": interior_only_rhs(space, layout),
                   "physical": physical, "notch_supported": supported}
        for name, rhs in sources.items():
            save_array(name+"_rhs", rhs)
        old_oracle.require_fixture(input_sha, axes, layout, base, generic)
        matrix_bytes = 2048**2*16

        def assemble(volume):
            expansion = _mpc_expansion_width(floquet.mpc, layout.full_rows)
            graph = 80*int(space.element.space_dimension)**2*expansion**2+layout.full_rows
            integer_admission((layout.full_rows, layout.full_rows), graph, index_dtype=PETSc.IntType)
            sparse_bytes = graph*(16+np.dtype(PETSc.IntType).itemsize)+(layout.full_rows+1)*np.dtype(PETSc.IntType).itemsize
            allocation_gate("original_full_FFCx_dense_p2", {"matrix_payload_bytes": matrix_bytes+sparse_bytes,
                "workspace_bytes": 3*sparse_bytes, "nnz_upper": graph, "measured_mpc_expansion_width": expansion})
            return assemble_original_dense(volume, floquet, base["dtn_action"].carrier, layout)

        action0 = FullOriginalAction(base["physical_action"], layout)
        a0 = assemble(base["volume_action"])
        save_array("A0_original", a0)
        # A physical operator correction, not an equality gate to the old floor-clipped carrier.
        allocation_gate("old_clipped_operator_delta_stream", {"matrix_payload_bytes": matrix_bytes,
                        "workspace_bytes": 3*2048*32*16, "mmap_pages_counted": True})
        old = old_oracle.load("A0_original")
        error_sq = new_sq = old_sq = maximum = 0.0
        for j in range(0, 2048, 32):
            aa, bb = a0[:, j:j+32], old[:, j:j+32]
            delta = aa-bb
            error_sq += float(np.vdot(delta, delta).real)
            new_sq += float(np.vdot(aa, aa).real); old_sq += float(np.vdot(bb, bb).real)
            maximum = max(maximum, float(np.max(np.abs(delta))))
        operator_delta = {"relative_frobenius_to_centered": float(np.sqrt(error_sq/new_sq)),
            "relative_frobenius_to_old_clipped": float(np.sqrt(error_sq/old_sq)),
            "absolute_entry_max": maximum, "all_columns": 2048, "not_an_equivalence_gate": True,
            "physical_RHS_delta_relative": _relative(physical-old_oracle.load("physical_rhs"), physical)}
        del old, delta, aa, bb
        event("centered_operator_ready", {"identity": {k:v for k,v in identity.items() if k != "actual_context"},
                                          "old_clipped_operator_delta": operator_delta})
        errors = []
        for rhs in (generic, np.conj(generic), sources["interior_only"], supported):
            errors.append(_relative(a0@rhs-action0.apply(rhs), a0@rhs))
        if max(errors) > LIMITS["operator"]:
            raise ValueError("fresh centered original FFCx matrix/action disagrees")
        if live_component_oracle:
            require_live_carrier_unchanged(base,identity,event=event,boundary="before_full_A0_factor",expected_carrier=qualified_carrier)
        allocation_gate("full_p2_direct_factor", {"matrix_payload_bytes": matrix_bytes,
             "workspace_bytes": 512 << 20, "declared_factor_workspace_not_fill_bound": True})
        lu = lu_factor(np.array(a0, order="F"), overwrite_a=True, check_finite=True)
        direct0 = {name: lu_solve(lu, rhs, check_finite=True) for name, rhs in sources.items()}
        del lu
        allocation_gate("full_p2_modal_reference", {"matrix_payload_bytes": 4*matrix_bytes,
                        "workspace_bytes": 32 << 20, "full_p2_only": True})
        inverse = YReferenceInverse(a0, layout)
        regular = {}
        for name, rhs in sources.items():
            direct = direct0[name]; save_array("A0_direct_"+name, direct)
            packet = original_packet(base, layout, rhs, direct, label="direct_regular_"+name, save=save_array)
            _check_packet(packet)
            packet["outputs"] = recovered_field_and_modes(base, layout, direct, physical=name=="physical",
                                                          label="direct_regular_"+name, save=save_array)
            require_output_packet(packet["outputs"],label="direct_regular_"+name,event=event)
            solution = inverse.apply_array(rhs); save_array("A0_modal_"+name, solution)
            candidate = original_packet(base, layout, rhs, solution, label="regular_"+name, save=save_array)
            _check_packet(candidate)
            candidate["relative_direct_solution_difference"] = _relative(solution-direct, direct)
            if candidate["relative_direct_solution_difference"] > LIMITS["solution"]:
                raise ValueError("centered all-q full original inverse differs from direct control")
            candidate["outputs"] = recovered_field_and_modes(base, layout, solution, physical=name=="physical",
                                                             label="regular_"+name, save=save_array)
            require_output_packet(candidate["outputs"],label="regular_"+name,event=event)
            regular[name] = {"direct": packet, "candidate": candidate}
        mesh_data = SimpleNamespace(**vars(levels["mesh_data"])); mesh_data.cell_tags = tags
        notch_audit = _rectangular_air_void_audit(levels["mesh"], tags, notch_cfg)
        mesh_data.rectangular_air_void_audit = notch_audit
        volume1 = _build_split_volume_action(mesh_data, notch_cfg, space, floquet, jit_options={})
        notched = FullspacePhysicalAction(volume1, base["dtn_action"], owns_dtn=False)
        action1 = FullOriginalAction(notched, layout)
        notch_bundle = {**base, "cfg": notch_cfg, "volume_action": volume1,
                        "physical_action": notched, "action": notched}
        a1 = assemble(volume1); save_array("A_notch_original", a1)
        allocation_gate("notch_delta_modal_congruence", {"matrix_payload_bytes": 3*matrix_bytes,
                        "workspace_bytes": matrix_bytes})
        from .task40extra_y_orbit_reference import _congruence
        delta = _congruence(a1-a0, layout.q)
        norm = np.linalg.norm(delta)
        for q in range(4):
            rows = slice(q*512, (q+1)*512); delta[rows, rows] = 0
        off_q = float(np.linalg.norm(delta)/norm)
        del delta, a0
        if off_q < 1e-8:
            raise ValueError("actual full3D notch must couple distinct y blocks")
        notch_matrix_error = max(_relative(a1@rhs-action1.apply(rhs), a1@rhs) for rhs in sources.values())
        if notch_matrix_error > LIMITS["operator"]:
            raise ValueError("fresh centered notch original FFCx matrix/action disagrees")
        if live_component_oracle:
            require_live_carrier_unchanged(base,identity,event=event,boundary="before_full_A1_factor",expected_carrier=qualified_carrier)
        allocation_gate("full_p2_notch_direct_factor", {"matrix_payload_bytes": matrix_bytes,
                        "workspace_bytes": 512 << 20})
        lu = lu_factor(np.array(a1, order="F"), overwrite_a=True, check_finite=True)
        direct1 = {name: lu_solve(lu, rhs, check_finite=True) for name, rhs in sources.items()}
        del lu
        notch = {}
        for name, rhs in sources.items():
            direct = direct1[name]; save_array("notch_direct_"+name, direct)
            packet = original_packet(notch_bundle, layout, rhs, direct, label="direct_notch_"+name, save=save_array)
            _check_packet(packet)
            packet["outputs"] = recovered_field_and_modes(notch_bundle, layout, direct, physical=name=="physical",
                                                          label="direct_notch_"+name, save=save_array)
            require_output_packet(packet["outputs"],label="direct_notch_"+name,event=event)
            solution, krylov = solve_notched_fgmres(action1, inverse, rhs)
            save_array("notch_iterative_"+name, solution)
            candidate = original_packet(notch_bundle, layout, rhs, solution, label="notch_"+name, save=save_array)
            _check_packet(candidate); candidate.update(krylov)
            candidate["relative_direct_solution_difference"] = _relative(solution-direct, direct)
            norms = np.asarray(candidate["solution_primal_q_norms"])
            candidate["nonzero_q_primal_relative"] = float(np.linalg.norm(norms[1:])/np.linalg.norm(norms))
            if (candidate["reason"] <= 0 or candidate["relative_direct_solution_difference"] > LIMITS["solution"]
                    or (name == "physical" and candidate["nonzero_q_primal_relative"] <= LIMITS["notch_modes"])):
                raise ValueError("centered full3D notch candidate/direct/physical nonzero-q gate failed")
            candidate["outputs"] = recovered_field_and_modes(notch_bundle, layout, solution, physical=name=="physical",
                                                             label="notch_"+name, save=save_array)
            require_output_packet(candidate["outputs"],label="notch_"+name,event=event)
            notch[name] = {"direct": packet, "candidate": candidate}
        if live_component_oracle:
            require_live_carrier_unchanged(base,identity,event=event,boundary="dense_workflow_exit",expected_carrier=qualified_carrier)
        return {"schema": "task40extra.centered-dense-p2-authority.v1", "status": "CENTERED_DENSE_AUTHORITY_PASS",
                "degree": 2, "dtn_phase_gauge": "boundary_plane", "live_component_oracle": live_component_oracle, "reference_scope": CENTERED_SCOPE,
                "identity": identity, "input_sha256": input_sha, "axes_nm": {k:list(v) for k,v in axes.items()},
                "azimuth_deg": 5.0, "seed": SEED, "limits": LIMITS, "source_names": list(SOURCES),
                "layout": layout.audit, "ports": ports, "physical_rhs_facts": physical_facts,
                "matrix_vs_original_action_relative": max(errors), "notch_matrix_vs_original_action_relative": notch_matrix_error,
                "reference_inverse": inverse.audit, "regular_sources": regular, "notched_sources": notch,
                "changed_cells": changed.tolist(), "notch_geometry_audit": notch_audit,
                "notch_supported_RHS": support_facts, "notch_delta_off_q_relative": off_q,
                "old_clipped_operator_delta": operator_delta, "component_accuracy_is_not_continuum": True,
                "official_RTA": False, "target_geometry_accuracy": False, "no_2TB_or_48h_claim": True}
    finally:
        if action1 is not None: action1.close()
        if action0 is not None: action0.close()
        if notched is not None: notched.destroy()
        if base is not None: destroy_same_mesh_physical_action(base)
