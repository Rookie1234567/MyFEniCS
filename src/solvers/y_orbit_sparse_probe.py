"""Numerical workflow for the staged sparse-p2 bridge and p4 degree probe.

The p2 case is compared to the hash-bound saved dense authority; it is a
qualification bridge for exact condensation and sparse congruence, not another
physical parameter study.  The p4 case keeps the same 80 cells, materials,
wavelength, two-cell nonseparable notch and all 532 physical port channels.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
from scipy import sparse

from src.solvers.task40extra_y_orbit_reference import (
    LIMITS, SEED, FullOriginalAction, _relative, build_y_orbit_layout, pilot_config,
    solve_notched_fgmres,
)
from src.solvers.y_orbit_condensed_adapter import (
    assemble_sparse_p2_volume, audit_original_solution, audit_recovered_translation,
    build_condensed_reference, compare_p2_saved_dense, coordinate_array_views,
    recovery_numeric_identity, trace_layout_coordinates,
)
from src.solvers.y_orbit_sparse_reference import (
    SCHEMA, SparseAllQFactor, FullRecoveredReferenceInverse, _gate,
    audit_condensation_covariance, audit_full_form_covariance,
    build_augmented_coordinates, csr_audit, integer_admission, sampled_right_pc_defect,
)


def _save_csr(save_array, prefix, matrix):
    for suffix in ("data", "indices", "indptr"):
        save_array(prefix + "_" + suffix, getattr(matrix, suffix))


def _check_packet(packet):
    keys = ("full_original_true_residual", "augmented_FE_true_residual",
            "augmented_port_closure_relative")
    if (any(not np.isfinite(packet[key]) or packet[key] > LIMITS["residual"] for key in keys)
            or packet["full_native_slave_zero"] is not True):
        raise ValueError(f"full original recovered residual gate fails: {packet}")
    identity = packet["augmented_residual_identity"]
    # The helper's explicit identity is evidence independent of the condensed
    # factor. Its fields are recorded verbatim and validated by the checker.
    if (not isinstance(identity, dict) or identity.get("passed") is not True
            or not np.isfinite(identity.get("relative", float("nan")))
            or identity["relative"] > identity["limit"]):
        raise ValueError("missing inherited augmented residual identity")


def _packet_with_vectors(reference, layout, rhs, solution, *, label, save_array,
                         auxiliary_ports=None):
    packet = audit_original_solution(reference, layout, rhs, solution,
                                     auxiliary_ports=auxiliary_ports, return_vectors=True)
    vectors = packet.pop("vectors")
    for name, values in vectors.items():
        save_array(label + "_" + name, values)
    packet["solution_primal_q_norms"] = layout.modal_norms(solution, dual=False)
    return packet


def _notch_supported_rhs(space, layout, changed):
    native = np.unique(np.concatenate([space.dofmap.cell_dofs(int(cell)) for cell in changed]))
    positions = np.flatnonzero(np.isin(layout.independent, native))
    rhs = np.zeros(len(layout.independent), dtype=np.complex128)
    phase = np.arange(len(positions))
    rhs[positions] = np.cos(0.31 * phase) + 1j * np.sin(0.47 * phase)
    rhs /= np.linalg.norm(rhs)
    return rhs, {"support_actual_changed_cells": changed.tolist(),
                 "support_independent_rows": len(positions),
                 "full_original_FE_load": True, "seed_formula": "cos(.31j)+i sin(.47j)"}


def run_sparse_probe(input_path, *, degree, event, save_array, allocation_gate,
                     saved_oracle=None, auxiliary_gauge="raw", save_factor_diagnostic=None,
                     dtn_phase_gauge="global_z", live_component_oracle=False, live_component_record_path=None):
    from mpi4py import MPI
    from petsc4py import PETSc
    from src.geometry.mesh_builder_3d import _mark_cells, _rectangular_air_void_audit
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        _build_split_volume_action, build_physical_rhs, build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )
    from src.solvers.fullspace_physical_action import FullspacePhysicalAction
    centered = dtn_phase_gauge == "boundary_plane"
    if live_component_oracle and not centered: raise ValueError("live component oracle requires centered p2")
    if dtn_phase_gauge not in ("global_z", "boundary_plane") or (centered and (degree != 2 or auxiliary_gauge != "positive-h")):
        raise ValueError("centered p2 positive-H only; p4 requires separate admission")

    if degree not in (2, 4) or (degree == 2 and saved_oracle is None):
        raise ValueError("only saved-authority sparse-p2 bridge or same-mesh p4 is admitted")
    cfg, axes, input_sha = pilot_config(input_path, azimuth_deg=5.0)
    if degree == 4:
        cfg = replace(cfg, nedelec_degree=4, visualization_degree=4,
                      case_name="y_orbit_p4_algebra_regular")
    nx, ny, nz = (len(axes[key]) - 1 for key in ("x", "y", "z"))
    expected_independent = nx * ny * degree**2 * (3 * nz * degree + 2)
    expected_interiors = nx * ny * nz * 3 * degree * (degree - 1)**2
    expected_trace = expected_independent - expected_interiors
    integer_admission((expected_independent, expected_independent),
                      nx * ny * nz * (3 * degree * (degree + 1)**2)**2,
                      index_dtype=PETSc.IntType)
    event("degree_only_full3D_setup_begin", {"degree": degree, "cells": 80,
                                            "no_hidden_p6_space": True})
    levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (degree,), include_positive_coefficients=False)
    space, floquet = levels["spaces"][degree], levels["floquets"][degree]
    if int(levels["mesh"].topology.index_map(3).size_local) != 80 or set(levels["spaces"]) != {degree}:
        raise ValueError("require exactly the unchanged 80 full3D cells and only requested degree")
    # Full orbit-map construction includes Python list work for exact entity
    # orientation. Admit a deliberately loose bound before using the existing
    # map builder. This bound is not its measured RSS or a scaling predictor.
    dense_entity_width = max(3 * degree * (degree - 1)**2, 2 * degree * (degree - 1), degree)
    map_nnz_upper = expected_independent * dense_entity_width
    _gate(allocation_gate, "full_Hcurl_orbit_map",
          payload=map_nnz_upper * 40 + expected_independent * ny * 20,
          workspace=map_nnz_upper * 224,
          exact_entity_orientation_no_small_entry_threshold=True)
    layout = build_y_orbit_layout(space, floquet, cfg, axes)
    if (len(layout.independent) != expected_independent
            or int(layout.audit["dimension_dof_counts"][3]) != expected_interiors):
        raise ValueError("actual full FE rows/interiors differ from the complete tensor inventory")
    event("full_layout_ready", layout.audit)
    for name, matrix in (("full_Q", layout.q), ("full_R_inverse", layout.r_inverse),
                         ("full_F", layout.fourier), ("full_T", layout.native_translation)):
        _save_csr(save_array, name, matrix)
    save_array("independent_storage_rows", layout.independent)
    base = reference = factor = action0 = action1 = notched_action = None
    try:
        base = build_same_mesh_physical_action(levels, cfg, degree, dtn_phase_gauge=dtn_phase_gauge)
        centered_facts = None
        if centered:
            from .y_orbit_centered_evidence import (
                centered_identity, interior_only_rhs, recovered_field_and_modes, save_mpc_inventory,
                require_output_packet, fixture_interior_positions,
            )
            if live_component_oracle:
                from .y_orbit_live_boundary_contract import qualify_live_identity, require_live_carrier_unchanged
                if live_component_record_path is None: raise ValueError("same-live component record path required")
                centered_facts = qualify_live_identity(base,record_path=live_component_record_path,
                                                       allocation_gate=allocation_gate,event=event)
                qualified_carrier = base["dtn_action"].carrier
            else:
                centered_facts = centered_identity(base,event=event)
            save_mpc_inventory(base, layout, save_array)
            save_array("actual_interior_positions",fixture_interior_positions(space,layout))
        action0 = FullOriginalAction(base["physical_action"], layout)
        rng = np.random.default_rng(SEED)
        generic = rng.standard_normal(expected_independent) + 1j * rng.standard_normal(expected_independent)
        excitation = np.asarray(layout.modal_norms(generic, dual=True))
        if np.min(excitation) / np.linalg.norm(excitation) < LIMITS["excitation"]:
            raise ValueError("generic full FE dual RHS must excite every q")
        reference = build_condensed_reference(base, allocation_gate=allocation_gate)
        if (reference.system.active_rows != expected_trace
                or reference.system.active_interior_rows != expected_interiors
                or reference.system.appended_rows != len(base["modes"])):
            raise ValueError("condensed trace/interior/port inventory is incomplete")
        trace = trace_layout_coordinates(layout, reference.system, allocation_gate=allocation_gate)
        for name, values in coordinate_array_views(trace):
            save_array("trace_" + name, values)
        coordinates = build_augmented_coordinates(trace, layout, reference.carrier, base["modes"], cfg,
                                                  allocation_gate=allocation_gate,
                                                  petsc_index_dtype=PETSc.IntType,
                                                  auxiliary_gauge=auxiliary_gauge)
        expected_ports = 2 * (2 * cfg.diffraction_order_max_m + 1) * (2 * cfg.diffraction_order_max_n + 1) * 2
        if len(base["modes"]) != expected_ports:
            raise ValueError("fresh actual manual generator differs from complete side/order/polarization count")
        save_array("port_q_labels", np.asarray([key[2] % ny for key in coordinates.original_port_keys]))
        save_array("port_eta", coordinates.eta_ports)
        save_array("port_original_H", np.asarray([e.normalization_h for e in reference.carrier.entries]))
        save_array("port_factor_coordinate_scale", coordinates.scale)
        full_covariance = audit_full_form_covariance(action0, layout, (generic, np.conj(generic)))
        reduce_covariance = audit_condensation_covariance(reference, layout, coordinates,
                                                         (generic, np.conj(generic)),
                                                         allocation_gate=allocation_gate)
        recovery_identity = recovery_numeric_identity(reference)
        matrix = reference.scipy_csr(allocation_gate=allocation_gate)
        matrix_facts = csr_audit(matrix, petsc_index_dtype=PETSc.IntType)
        _save_csr(save_array, "reference_S", matrix)
        if degree == 2:
            (saved_oracle.require_fixture(input_sha, axes, layout, base, generic, live_identity=centered_facts)
             if live_component_oracle else saved_oracle.require_fixture(input_sha, axes, layout, base, generic))
            volume = assemble_sparse_p2_volume(base, layout, allocation_gate=allocation_gate)
            original_p2_csr = csr_audit(volume, petsc_index_dtype=PETSc.IntType)
            bridge = compare_p2_saved_dense(volume, reference.carrier, layout,
                                           saved_oracle.load("A0_original"),
                                           allocation_gate=allocation_gate)
            del volume
            if bridge["passed"] is not True:
                raise ValueError(f"sparse p2 original operator differs from saved dense authority: {bridge}")
            event("saved_dense_p2_all_columns_pass", bridge)
        else:
            bridge = original_p2_csr = None
        if live_component_oracle:
            require_live_carrier_unchanged(base,centered_facts,event=event,boundary="before_all_q_factors",expected_carrier=qualified_carrier)
        factor = SparseAllQFactor(matrix, coordinates, allocation_gate=allocation_gate,
                                  event=event, save_array=save_array,
                                  save_factor_diagnostic=save_factor_diagnostic)
        inverse = FullRecoveredReferenceInverse(reference, layout, factor)
        del matrix
        physical_storage, physical_rhs_facts = build_physical_rhs(base)
        try:
            physical = physical_storage.getArray(readonly=True)[layout.independent].copy()
        finally:
            physical_storage.destroy()
        sources = {"generic": generic, "physical": physical}
        if centered:
            pre_scale = 7/135
            pre_box = tuple(value*pre_scale for value in (25, 33.5, 6.25, 18.75, 40, 80))
            pre_cfg = replace(cfg, case_name="y_orbit_p2_algebra_notch", air_void_box_nm=pre_box,
                              geometry_identity=cfg.geometry_identity+".notch")
            pre_tags = _mark_cells(levels["mesh"], pre_cfg)
            pre_changed = np.flatnonzero(pre_tags.values != levels["mesh_data"].cell_tags.values)
            if len(pre_changed) != 2:
                raise ValueError("centered source support must be the actual unchanged two-cell notch")
            sources["interior_only"] = interior_only_rhs(space, layout)
            sources["notch_supported"], _ = _notch_supported_rhs(space, layout, pre_changed)
            from .y_orbit_centered_evidence import SOURCES
            sources = {name: sources[name] for name in SOURCES}
            for name,rhs in sources.items():
                if not np.array_equal(rhs, saved_oracle.load(name+"_rhs")):
                    raise ValueError("centered sparse full FE forcing differs from fresh dense authority: "+name)
        if degree == 2 and _relative(physical - saved_oracle.load("physical_rhs"), physical) > LIMITS["operator"]:
            raise ValueError("current physical RHS differs from the saved phi5 authority")
        regular = {}
        for label, rhs in sources.items():
            save_array(label + "_rhs", rhs)
            solution = inverse.apply_array(rhs)
            save_array("regular_" + label + "_solution", solution)
            packet = _packet_with_vectors(reference, layout, rhs, solution, label="regular_" + label,
                                          save_array=save_array,
                                          auxiliary_ports=reference.inverse.last_port_solution.copy())
            _check_packet(packet)
            recovered_translation = audit_recovered_translation(reference, layout, rhs, solution)
            _check_packet(recovered_translation)
            packet["full_recovered_translation"] = recovered_translation
            if degree == 2:
                direct = saved_oracle.load("A0_direct_" + label)
                packet["saved_dense_direct_difference"] = _relative(solution - direct, direct)
                if packet["saved_dense_direct_difference"] > LIMITS["solution"]:
                    raise ValueError("sparse-condensed p2 inverse disagrees with saved original direct control")
            if centered:
                packet["outputs"] = recovered_field_and_modes(base, layout, solution, physical=label=="physical",
                                          label="regular_"+label, save=save_array)
                require_output_packet(packet["outputs"],label="regular_"+label,event=event)
            regular[label] = packet
            event("regular_recovered_inverse_pass", {"label": label,
                   "original_residual": packet["full_original_true_residual"]})

        scale = 7 / 135
        box = tuple(value * scale for value in (25, 33.5, 6.25, 18.75, 40, 80))
        notch_cfg = replace(cfg, case_name=f"y_orbit_p{degree}_algebra_notch", air_void_box_nm=box,
                            geometry_identity=cfg.geometry_identity + ".notch")
        tags = _mark_cells(levels["mesh"], notch_cfg)
        changed = np.flatnonzero(tags.values != levels["mesh_data"].cell_tags.values)
        if len(changed) != 2:
            raise ValueError("same unchanged mesh must retain the genuine two-cell nonseparable notch")
        mesh_data = SimpleNamespace(**vars(levels["mesh_data"]))
        mesh_data.cell_tags = tags
        notch_audit = _rectangular_air_void_audit(levels["mesh"], tags, notch_cfg)
        mesh_data.rectangular_air_void_audit = notch_audit
        volume1 = _build_split_volume_action(mesh_data, notch_cfg, space, floquet, jit_options={})
        notched_action = FullspacePhysicalAction(volume1, base["dtn_action"], owns_dtn=False)
        action1 = FullOriginalAction(notched_action, layout)
        notched_bundle = {**base, "cfg": notch_cfg, "volume_action": volume1,
                          "physical_action": notched_action, "action": notched_action}
        # Residual-only borrowed view: never construct/recover a second Schur
        # system, and never destroy this view independently of the reference.
        notch_reference = replace(reference, action_bundle=notched_bundle)
        cross_squared = full_squared = 0.0
        sampled_delta = []
        for q in range(ny):
            modal_source = np.zeros(expected_independent, dtype=np.complex128)
            rows = slice(q * layout.width, (q + 1) * layout.width)
            modal_source[rows] = np.cos(.37 * np.arange(layout.width)) + 1j * np.sin(.23 * np.arange(layout.width))
            source = layout.primal_from_modal(modal_source)
            delta = layout.dual_to_modal(action1.apply(source) - action0.apply(source))
            all_norm = np.linalg.norm(delta)
            delta[rows] = 0.0
            cross_norm = np.linalg.norm(delta)
            full_squared += float(all_norm**2)
            cross_squared += float(cross_norm**2)
            sampled_delta.append({"source_q": q, "delta_dual_norm": float(all_norm),
                                  "off_q_delta_dual_norm": float(cross_norm)})
        sampled_cross_relative = float(np.sqrt(cross_squared / max(full_squared, np.finfo(float).tiny)))
        if sampled_cross_relative < 1e-8:
            raise ValueError("actual notch action must couple distinct y blocks in the complete FE space")
        supported, supported_facts = _notch_supported_rhs(space, layout, changed)
        sources["notch_supported"] = supported
        if centered and not np.array_equal(supported, saved_oracle.load("notch_supported_rhs")):
            raise ValueError("actual centered notch support differs from fresh dense authority")
        save_array("notch_supported_rhs", supported)
        perturbation = {}
        notch = {}
        for label, rhs in sources.items():
            perturbation[label] = sampled_right_pc_defect(action0, action1, inverse, rhs)
            solution, krylov = solve_notched_fgmres(action1, inverse, rhs)
            save_array("notch_" + label + "_solution", solution)
            # PC's last auxiliary solves A0, not A1: recover A1 ports from the
            # final original FE field, rather than reusing its last PC alpha.
            packet = _packet_with_vectors(notch_reference, layout, rhs, solution,
                                          label="notch_" + label, save_array=save_array)
            _check_packet(packet)
            packet.update(krylov)
            norms = np.asarray(packet["solution_primal_q_norms"])
            packet["nonzero_q_primal_relative"] = float(np.linalg.norm(norms[1:]) / np.linalg.norm(norms))
            if label == "physical" and packet["nonzero_q_primal_relative"] <= LIMITS["notch_modes"]:
                raise ValueError("actual notch physical field must contain nonzero y blocks")
            if packet["reason"] <= 0:
                raise ValueError("FGMRES did not give a positive converged reason")
            if degree == 2 and (centered or label in ("generic", "physical")):
                direct = saved_oracle.load("notch_direct_" + label)
                packet["saved_dense_direct_difference"] = _relative(solution - direct, direct)
                if packet["saved_dense_direct_difference"] > LIMITS["solution"]:
                    raise ValueError("sparse p2 notched original solve disagrees with saved dense direct")
            if centered:
                packet["outputs"] = recovered_field_and_modes(notched_bundle, layout, solution, physical=label=="physical",
                                           label="notch_"+label, save=save_array)
                require_output_packet(packet["outputs"],label="notch_"+label,event=event)
            notch[label] = packet
            event("notch_full3D_solve_pass", {"label": label, "iterations": packet["iterations"],
                  "original_residual": packet["full_original_true_residual"],
                  "sampled_right_pc_defect": perturbation[label]})
        final_recovery_identity = recovery_numeric_identity(reference)
        if recovery_identity != final_recovery_identity:
            raise ValueError("exact original recovery numeric state changed during applies")
        if live_component_oracle:
            require_live_carrier_unchanged(base,centered_facts,event=event,boundary="sparse_workflow_exit",expected_carrier=qualified_carrier)
        return {"schema": SCHEMA, "status": "SPARSE_CONDENSED_FULL3D_PROBE_PASS",
                "degree": degree, "azimuth_deg": 5.0, "cells": 80,
                "auxiliary_gauge": auxiliary_gauge,
                "reference_scope": ("fresh boundary-plane FE operator; original cutoffs and all physical contributions audited"
                                    if centered else "same frozen upstream-clipped FE operator; no lost functional restored"),
                "dtn_phase_gauge": dtn_phase_gauge, "centered_identity": centered_facts,
                "live_component_oracle": live_component_oracle,
                "input_sha256": input_sha, "axes_nm": {k: list(v) for k, v in axes.items()},
                "mode_manifest_sha256": base["mode_sha256"], "mode_keys": coordinates.original_port_keys,
                "physical_rhs_facts": physical_rhs_facts, "limits": LIMITS,
                "seed": SEED, "layout": layout.audit, "coordinates": coordinates.audit,
                "condensation": reference.audit, "recovery_numeric_identity": recovery_identity,
                "condensed_matrix": matrix_facts, "reference_factor": factor.audit,
                "full_form_covariance": full_covariance, "complete_RHS_covariance": reduce_covariance,
                "original_p2_sparse_matrix": original_p2_csr, "saved_dense_p2_bridge": bridge,
                "regular_sources": regular, "notched_sources": notch,
                "changed_cells": changed.tolist(), "notch_geometry_audit": notch_audit,
                "notch_supported_RHS": supported_facts,
                "sampled_right_PC_defect": perturbation, "PC_defect_is_norm_bound": False,
                "sampled_notch_off_q_delta_relative": sampled_cross_relative,
                "sampled_notch_q_coupling": sampled_delta,
                "sampled_notch_delta_is_operator_norm": False,
                "full_p4_direct_control": "not_run_not_admitted" if degree == 4 else "saved_p2_only",
                "target_geometry_accuracy": False, "production_default_qualification": False,
                "official_RTA": False, "same_mesh_degree_growth_only": degree == 4,
                "no_2TB_or_48h_claim": True, "all_q_factor_calls": factor.calls,
                "all_full_recovery_calls": inverse.calls}
    finally:
        if action1 is not None:
            action1.close()
        if action0 is not None:
            action0.close()
        if notched_action is not None:
            notched_action.destroy()
        if reference is not None:
            reference.destroy()
        if factor is not None:
            factor.destroy()
        if base is not None:
            destroy_same_mesh_physical_action(base)
