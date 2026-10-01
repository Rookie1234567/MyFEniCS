"""Staged gauge tests, all NOT RUN. No global PDE factor is required.

The all-mode oracle uses separate literal UFL forms, full actual MPC, the
same Gauss rule, and all independent 3D FE coordinates. It does not assume
that fresh centered stored coefficients equal the clipped old carrier.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.dtn_boundary_phase_gauge import (
    GLOBAL_Z, BOUNDARY_PLANE, assembly_projection_denominator,
    global_amplitudes_from_solver, solver_amplitudes_from_global,
    plane_port_rhs_from_global, global_port_rhs_from_plane,
    incident_projection_in_solver_coordinates, outgoing_solver_amplitudes,
    boundary_mode_power_from_solver, phase_gauge_descriptor,
    prepare_boundary_plane_outputs, deep_frozen_identity,
    compiled_surface_quadrature_identity,
    analytic_lossless_evanescent_zero_power,
)


def _cfg():
    return SimpleNamespace(physical_z_min=-0.3, physical_z_max=1.0,
                           x_min=0.0, x_max=2.0, y_min=0.0, y_max=1.0,
                           n_air=1+0j, k0=1.0, mu_r=1+0j, kz=-0.5,
                           incident_amplitude=1+0j, polarization_vector=np.array([1, 0, 0]))


def _mode(side="top", kz=0.5, index=0):
    return SimpleNamespace(side=side, m=index, n=0, polarization="s",
                           k_vector=np.array([0, 0, kz], dtype=np.complex128),
                           e_vector=np.array([1, 0, 0], dtype=np.complex128),
                           electric_tangential_norm_sq=1.0)


def _relative(left, right):
    difference = np.linalg.norm(left - right)
    scale = np.linalg.norm(left) + np.linalg.norm(right)
    return float(difference / scale) if scale else (0.0 if difference == 0 else float("inf"))


def test_complex_augmented_nonzero_rhs_and_outgoing_coordinate_contract():
    cfg = _cfg()
    modes = [_mode(kz=0.3+2j), _mode(kz=-0.4+0.7j, index=1), _mode("bottom", -0.6-3j, 2)]
    scales = np.array([np.exp(1j*m.k_vector[2]*(cfg.physical_z_max if m.side == "top" else cfg.physical_z_min))
                       for m in modes])
    rng = np.random.default_rng(4053201)
    C = rng.normal(size=(4, 3)) + 1j*rng.normal(size=(4, 3))
    D = rng.normal(size=(3, 4)) + 1j*rng.normal(size=(3, 4))
    V = rng.normal(size=(4, 4)) + 1j*rng.normal(size=(4, 4))
    H = np.array([1.1, 2.3+0.4j, 4.6-0.2j])  # General algebra supplement.
    global_aug = np.block([[V, C*scales], [-scales.conj()[:, None]*D, np.diag(abs(scales)**2*H)]])
    plane_aug = np.block([[V, C], [-D, np.diag(H)]])
    x = rng.normal(size=(4, 5)) + 1j*rng.normal(size=(4, 5))
    a = rng.normal(size=(3, 5)) + 1j*rng.normal(size=(3, 5))
    b = solver_amplitudes_from_global(a, modes, cfg, BOUNDARY_PLANE)
    rhs_global = global_aug @ np.vstack([x, a])
    rhs_plane = np.vstack([rhs_global[:4], plane_port_rhs_from_global(rhs_global[4:], modes, cfg, BOUNDARY_PLANE)])
    np.testing.assert_allclose(plane_aug @ np.vstack([x, b]), rhs_plane, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(global_amplitudes_from_solver(b, modes, cfg, BOUNDARY_PLANE), a,
                               rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(global_port_rhs_from_plane(rhs_plane[4:], modes, cfg, BOUNDARY_PLANE),
                               rhs_global[4:], rtol=1e-12, atol=1e-12)
    incident_global = 0.1*a
    incident_plane = solver_amplitudes_from_global(incident_global, modes, cfg, BOUNDARY_PLANE)
    np.testing.assert_allclose(
        global_amplitudes_from_solver(outgoing_solver_amplitudes(b, incident_plane, modes), modes, cfg, BOUNDARY_PLANE),
        outgoing_solver_amplitudes(a, incident_global, modes), rtol=1e-12, atol=1e-12,
    )
    np.testing.assert_array_equal(global_amplitudes_from_solver(a, modes, cfg, GLOBAL_Z), a)


def test_direct_plane_incident_and_power_equal_representable_global_contract():
    cfg, mode = _cfg(), _mode()
    incident_global = incident_projection_in_solver_coordinates(mode, cfg, GLOBAL_Z)
    incident_plane = incident_projection_in_solver_coordinates(mode, cfg, BOUNDARY_PLANE)
    scale = np.exp(1j*mode.k_vector[2]*cfg.physical_z_max)
    assert incident_plane == pytest.approx(scale*incident_global, rel=1e-12, abs=1e-12)
    a = 0.7-0.2j
    assert boundary_mode_power_from_solver(mode, cfg, a, GLOBAL_Z) == pytest.approx(
        boundary_mode_power_from_solver(mode, cfg, scale*a, BOUNDARY_PLANE), rel=1e-12, abs=1e-12,
    )


def test_direct_plane_H_and_power_do_not_require_representable_global_scale():
    cfg, mode = _cfg(), _mode(kz=1+1000j)
    assert assembly_projection_denominator(mode, cfg, BOUNDARY_PLANE) == 2.0
    assert boundary_mode_power_from_solver(mode, cfg, 1+0.2j, BOUNDARY_PLANE) > 0
    assert phase_gauge_descriptor(mode, cfg, BOUNDARY_PLANE)["log_abs_physical_boundary_phase"] == -1000
    with pytest.raises(FloatingPointError, match="unrepresentable"):
        global_amplitudes_from_solver([1], [mode], cfg, BOUNDARY_PLANE)
    plane = prepare_boundary_plane_outputs([1+0.2j], [0], [mode], cfg, include_global=False)
    assert plane["status"] == "plane_only_diagnostics" and plane["direct_plane_outgoing_power_diagnostic"][0] > 0
    stopped = prepare_boundary_plane_outputs([1+0.2j], [0], [mode], cfg)
    assert stopped["status"] == "controlled_stop_global_output_unrepresentable"
    assert stopped["global_output_failure"]["mode_index"] == 0
    assert stopped["plane_total_auxiliary"][0] == 1+0.2j
    assert stopped["direct_plane_outgoing_power_diagnostic"][0] > 0


def test_identity_is_recursively_frozen_and_power_underflow_rejected():
    original = {"phase_gauge": {"gauge": "boundary_plane"}, "context": {"mask": [1e-30, 1e-13]}}
    identity = deep_frozen_identity(original)
    original["phase_gauge"]["gauge"] = "wrong"
    assert identity["phase_gauge"]["gauge"] == "boundary_plane"
    with pytest.raises(TypeError):
        identity["phase_gauge"]["gauge"] = "wrong"
    cfg, mode = _cfg(), _mode(kz=1)
    with pytest.raises(FloatingPointError, match="unrepresentable"):
        boundary_mode_power_from_solver(mode, cfg, 1e-300, BOUNDARY_PLANE)


def test_conversion_rejects_overflow_nonzero_underflow_and_bad_shapes():
    cfg, mode = _cfg(), _mode(kz=1+450j)
    with pytest.raises(FloatingPointError, match="loses"):
        solver_amplitudes_from_global([1e-200], [mode], cfg, BOUNDARY_PLANE)
    with pytest.raises(FloatingPointError, match="overflows"):
        global_amplitudes_from_solver([1e200], [mode], cfg, BOUNDARY_PLANE)
    with pytest.raises(ValueError, match="shape"):
        plane_port_rhs_from_global(np.ones((1, 2, 3)), [mode], cfg, BOUNDARY_PLANE)
    with pytest.raises(ValueError, match="nonfinite"):
        global_amplitudes_from_solver([np.nan], [mode], cfg, BOUNDARY_PLANE)
    # Global total/incident can each be representable while their legacy
    # subtraction overflows. Plane diagnostics must survive that boundary.
    mode = _mode(kz=1+700j)
    stopped = prepare_boundary_plane_outputs([1e4], [-1e4], [mode], cfg)
    assert stopped["status"] == "controlled_stop_global_output_inconsistent"
    assert stopped["plane_outgoing_auxiliary"][0] == 2e4
    assert stopped["global_output_failure"]["mode_index"] == 0


def test_analytic_lossless_evanescent_signed_power_certificate():
    cfg = _cfg()
    mode = _mode(kz=1j*np.sqrt(3))
    mode.k_vector = np.array([2, 0, 1j*np.sqrt(3)], dtype=np.complex128)
    mode.e_vector = np.array([-1j*np.sqrt(3)/2, 0, 1], dtype=np.complex128)
    mode.refractive_index = 1+0j
    field = (0.6807367412098271+0.5502606205082826j)*mode.e_vector
    proof = analytic_lossless_evanescent_zero_power(mode, cfg, field)
    assert proof["proved"]
    assert abs(proof["raw_signed_power"]) <= proof["machine_epsilon_power_bound"]
    mode.e_vector = np.array([1, 0, 1], dtype=np.complex128)
    assert not analytic_lossless_evanescent_zero_power(mode, cfg, mode.e_vector)["proved"]


@pytest.mark.parametrize("kz,index", [(1+0j, 1+0j), (1+0.1j, 1+0.1j)])
def test_positive_power_propagating_or_lossy_underflow_is_not_exempt(kz, index):
    cfg, mode = _cfg(), _mode(kz=kz)
    mode.refractive_index = index
    assert not analytic_lossless_evanescent_zero_power(mode, cfg, mode.e_vector)["proved"]
    with pytest.raises(FloatingPointError, match="unrepresentable"):
        boundary_mode_power_from_solver(mode, cfg, 1e-300, BOUNDARY_PLANE)


@pytest.mark.skipif(os.environ.get("TASK40EXTRA_ALLOW_GAUGE_MPC_ORACLE") != "1",
                    reason="requires separate exact source/command/ABI/resource admission")
def test_actual_532_mode_same_gauss_full_mpc_coefficients_and_FE_action():
    from mpi4py import MPI
    from petsc4py import PETSc
    import ufl
    from dolfinx import fem
    from src.solvers.task40extra_y_orbit_reference import pilot_config
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action, build_physical_rhs, destroy_same_mesh_physical_action,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.dtn_port_3d import (
        _with_quadrature_degree, _assemble_mpc_form_vector, _set_scalar_constant,
        _traction_vector, _mode_projection_denominator,
    )
    assert MPI.COMM_WORLD.size == 1
    input_path = "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat"
    cfg, axes, input_hash = pilot_config(input_path, azimuth_deg=5.0)
    levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (2,), include_positive_coefficients=False)
    old = new = None
    raw_forms = {}
    try:
        old = build_same_mesh_physical_action(levels, cfg, 2, verify_dtn_quadrature=True)
        new = build_same_mesh_physical_action(levels, cfg, 2, dtn_phase_gauge=BOUNDARY_PLANE)
        modes = tuple(old["modes"])
        assert len(modes) == len(new["modes"]) == 532
        assert old["mode_sha256"] == new["mode_sha256"]
        assert old["dtn_quadrature_degree"] == new["dtn_quadrature_degree"]
        assert cfg.stage4_dtn_order_policy == "manual"
        assert cfg.diffraction_order_max_m == 9 and cfg.diffraction_order_max_n == 3
        old_carrier, new_carrier = old["dtn_action"].carrier, new["dtn_action"].carrier
        assert tuple(e.mode_key for e in old_carrier.entries) == tuple(e.mode_key for e in new_carrier.entries)
        assert old_carrier.mode_manifest_sha256 != new_carrier.mode_manifest_sha256
        assert new_carrier.physical_generator_manifest_sha256 == old["mode_sha256"]
        assert new_carrier.assembly_context["gauss"]["degree"] == old["dtn_quadrature_degree"]
        with pytest.raises(TypeError):
            new_carrier.entries[0].mode_identity["phase_gauge"]["gauge"] = "wrong"
        assert new_carrier.construction_numeric_inventory["unique_named_numpy_backing_bytes_before_staging_release"] <= 512 << 20
        V, mpc, mesh_data = levels["spaces"][2], levels["floquets"][2].mpc, levels["mesh_data"]
        n = int(V.dofmap.index_map.size_global)
        qdegree = int(old["dtn_quadrature_degree"])
        rng = np.random.default_rng(4053202)
        states = rng.normal(size=(n, 5)) + 1j*rng.normal(size=(n, 5))
        states[np.asarray(mpc.slaves, dtype=np.int64)] = 0
        assert states.nbytes <= 512 << 20
        accumulated = {name: np.zeros_like(states) for name in ("global_raw", "plane_raw", "old_stored", "new_stored")}
        ledger = []
        expected_recovery = {name: np.zeros((532, 5), dtype=np.complex128)
                             for name in ("old_stored", "new_stored", "plane_raw")}
        recovery_coefficient_scales = {name: np.zeros(532) for name in expected_recovery}
        oracle_gauss = {}
        vector_cache = None
        component_key = None
        # Independent literal UFL forms, same integral Gauss metadata and full
        # actual MPC. No primary surface/coefficient builder is called here.
        for gauge in (GLOBAL_Z, BOUNDARY_PLANE):
            for side in ("top", "bottom"):
                for component in (0, 1):
                    alpha = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0))
                    gamma = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0))
                    kz = fem.Constant(mesh_data.mesh, PETSc.ScalarType(0))
                    x = ufl.SpatialCoordinate(mesh_data.mesh)
                    z = x[2] if gauge == GLOBAL_Z else x[2]-PETSc.ScalarType(
                        cfg.physical_z_max if side == "top" else cfg.physical_z_min)
                    phase = ufl.exp(PETSc.ScalarType(1j)*(alpha*x[0]+gamma*x[1]+kz*z))
                    vector = [PETSc.ScalarType(0)]*3
                    vector[component] = phase
                    form = ufl.inner(ufl.as_vector(vector), ufl.TestFunction(V))*ufl.Measure(
                        "ds", domain=mesh_data.mesh, subdomain_data=mesh_data.facet_tags)(
                            cfg.tags.z_max if side == "top" else cfg.tags.z_min)
                    compiled = fem.form(_with_quadrature_degree(form, qdegree), jit_options=SAME_MESH_JIT_OPTIONS)
                    oracle_identity = compiled_surface_quadrature_identity(
                        _with_quadrature_degree(form, qdegree), compiled)
                    primary_bundle = old if gauge == GLOBAL_Z else new
                    primary_identity = primary_bundle["compiled_surface_gauss_identity"][f"{side}/{component}"]
                    assert oracle_identity["rules"] == primary_identity["rules"]
                    oracle_gauss[f"{gauge}/{side}/{component}"] = oracle_identity
                    raw_forms[(gauge, side, component)] = (alpha, gamma, kz, compiled)

        def dense_entry(entry, side):
            result = np.zeros(n, dtype=np.complex128)
            rows = entry.coupling_rows if side == "C" else entry.projection_rows
            values = entry.coupling_values if side == "C" else entry.projection_values
            result[rows] = values
            return result

        def loss_bound(C, D, Cref, Dref, H):
            # Stable full-DOF rank-one norm bound, without N×N matrices or
            # subtracting two nearly equal squared Frobenius expressions.
            return float((np.linalg.norm(C-Cref)*np.linalg.norm(D)
                         + np.linalg.norm(Cref)*np.linalg.norm(D-Dref))/H)

        for index, (mode, old_entry, new_entry) in enumerate(zip(modes, old_carrier.entries, new_carrier.entries, strict=True)):
            key = (mode.side, mode.m, mode.n, complex(mode.k_vector[2]))
            if key != component_key:
                vector_cache = {}
                for gauge in (GLOBAL_Z, BOUNDARY_PLANE):
                    components = []
                    for component in (0, 1):
                        alpha, gamma, kz, form = raw_forms[(gauge, mode.side, component)]
                        for constant, value in ((alpha, mode.alpha), (gamma, mode.gamma), (kz, mode.k_vector[2])):
                            _set_scalar_constant(constant, value)
                        raw = _assemble_mpc_form_vector(form, mpc)
                        try:
                            owned = raw.getOwnershipRange()
                            assert owned == (0, n)
                            components.append(np.asarray(raw.getArray(readonly=True), dtype=np.complex128).copy())
                        finally:
                            raw.destroy()
                    vector_cache[gauge] = components
                component_key = key
            gx, gy = vector_cache[GLOBAL_Z]
            px, py = vector_cache[BOUNDARY_PLANE]
            t = _traction_vector(mode, cfg)
            Cg, Cp = -t[0]*gx-t[1]*gy, -t[0]*px-t[1]*py
            Dg = np.conjugate(mode.e_vector[0]*gx+mode.e_vector[1]*gy)
            Dp = np.conjugate(mode.e_vector[0]*px+mode.e_vector[1]*py)
            z = cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min
            s = complex(np.exp(1j*mode.k_vector[2]*z))
            assert np.isfinite(s) and s != 0  # Honest bounded pilot representability gate.
            H = (cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*mode.electric_tangential_norm_sq
            Cgn, Dgn = Cg/s, Dg/np.conjugate(s)
            Hg = _mode_projection_denominator(mode, cfg)
            errors = {"raw_C_equivalence": _relative(Cgn, Cp), "raw_D_equivalence": _relative(Dgn, Dp),
                      "raw_H_equivalence": abs(Hg/(abs(s)**2)-H)/H}
            assert all(value <= 1e-10 for value in errors.values()), (index, errors)
            assert new_entry.normalization_h == pytest.approx(H, rel=1e-14)
            C_old, D_old = dense_entry(old_entry, "C")/s, dense_entry(old_entry, "D")/np.conjugate(s)
            C_new, D_new = dense_entry(new_entry, "C"), dense_entry(new_entry, "D")
            expected_recovery["old_stored"][index] = (D_old@states/H)/s
            expected_recovery["new_stored"][index] = D_new@states/H
            expected_recovery["plane_raw"][index] = Dp@states/H
            recovery_coefficient_scales["old_stored"][index] = np.linalg.norm(D_old)/(H*abs(s))
            recovery_coefficient_scales["new_stored"][index] = np.linalg.norm(D_new)/H
            recovery_coefficient_scales["plane_raw"][index] = np.linalg.norm(Dp)/H
            actions = {}
            for name, C, D in (("global_raw", Cgn, Dgn), ("plane_raw", Cp, Dp),
                               ("old_stored", C_old, D_old), ("new_stored", C_new, D_new)):
                actions[name] = C[:, None]*(D@states)[None, :]/H
                accumulated[name] += actions[name]
            errors["per_mode_raw_action_equivalence"] = _relative(actions["global_raw"], actions["plane_raw"])
            assert errors["per_mode_raw_action_equivalence"] <= 1e-10
            reference_norm = float(np.linalg.norm(Cp)*np.linalg.norm(Dp)/H)
            new_loss = loss_bound(C_new, D_new, Cp, Dp, H)
            normalized_loss = new_loss/reference_norm if reference_norm else (0 if new_loss == 0 else float("inf"))
            assert normalized_loss <= 1e-10, (index, "all-DOF coefficient certificate", normalized_loss)
            # Audit each unchanged sparsification stage independently. This is
            # an oracle policy application, not a production cutoff override.
            cutoffs = {}
            for label, components in (("global", (gx, gy)), ("plane", (px, py))):
                filtered = []
                component_counts = []
                for component in components:
                    cutoff = max(1e-30, 1e-13*float(np.max(np.abs(component))))
                    mask = np.abs(component) > cutoff
                    filtered.append(np.where(mask, component, 0))
                    component_counts.append({"raw_nonzero": int(np.count_nonzero(component)),
                                             "retained": int(np.count_nonzero(mask)), "cutoff": cutoff})
                Ccombined = -t[0]*filtered[0]-t[1]*filtered[1]
                Dcombined = np.conjugate(mode.e_vector[0]*filtered[0]+mode.e_vector[1]*filtered[1])
                cutoffs[label] = {"components": component_counts,
                                  "combined_C_cutoff": max(1e-30, 1e-13*float(np.max(np.abs(Ccombined)))),
                                  "combined_D_cutoff": max(1e-30, 1e-13*float(np.max(np.abs(Dcombined))))}
            # Full raw augmented port equation with an independent b and
            # nonzero rp: row scaling must use conjugate(s), not s.
            b = rng.normal(size=5) + 1j*rng.normal(size=5)
            rp_plane = H*b-Dp@states
            rp_global = Hg*(b/s)-Dg@states
            assert _relative(rp_global/np.conjugate(s), rp_plane) <= 1e-10
            incident_g = incident_projection_in_solver_coordinates(mode, cfg, GLOBAL_Z)
            incident_p = incident_projection_in_solver_coordinates(mode, cfg, BOUNDARY_PLANE)
            total_p = (Dp@states[:, 0])/H
            outgoing_p = total_p-incident_p if mode.side == "top" else total_p
            outgoing_g = (total_p/s)-incident_g if mode.side == "top" else total_p/s
            plane_power = boundary_mode_power_from_solver(mode, cfg, outgoing_p, BOUNDARY_PLANE)
            global_power = boundary_mode_power_from_solver(mode, cfg, outgoing_g, GLOBAL_Z)
            Eplane = outgoing_p*np.asarray(mode.e_vector)
            Hplane = np.cross(mode.k_vector, Eplane)/(cfg.k0*complex(cfg.mu_r))
            power_scale = 0.5*(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)*np.linalg.norm(Eplane)*np.linalg.norm(Hplane)
            power_error = abs(plane_power-global_power)/power_scale if power_scale else (0 if plane_power == global_power else float("inf"))
            assert power_error <= 1e-10
            ledger.append({
                "index": index, "key": list(old_entry.mode_key),
                "log_abs_s": float(np.log(abs(s))), "Hglobal": float(Hg), "Hplane": float(H),
                "raw_C_norm": float(np.linalg.norm(Cp)), "raw_D_norm": float(np.linalg.norm(Dp)),
                "raw_rank_one_Frobenius_norm": reference_norm,
                "old_C_entries": len(old_entry.coupling_rows), "old_D_entries": len(old_entry.projection_rows),
                "new_C_entries": len(new_entry.coupling_rows), "new_D_entries": len(new_entry.projection_rows),
                "old_stored_loss_bound": loss_bound(C_old, D_old, Cp, Dp, H),
                "new_stored_loss_bound": new_loss, "new_stored_relative_operator_bound": normalized_loss,
                "both_sparsification_stages": cutoffs,
                "plane_outgoing_power": plane_power, "global_outgoing_power": global_power,
                "power_operation_scaled_defect": float(power_error),
                "global_component_cutoffs": [max(1e-30, 1e-13*float(np.max(np.abs(v)))) for v in (gx, gy)],
                "plane_component_cutoffs": [max(1e-30, 1e-13*float(np.max(np.abs(v)))) for v in (px, py)],
                "equivalence": errors,
                "old_empty_does_not_prove_physical_zero": not len(old_entry.coupling_rows) or not len(old_entry.projection_rows),
            })
        assert len(ledger) == 532
        assert _relative(accumulated["global_raw"], accumulated["plane_raw"]) <= 1e-10
        assert _relative(accumulated["new_stored"], accumulated["plane_raw"]) <= 1e-10
        if "TASK40EXTRA_GAUGE_ORACLE_RECORD" in os.environ:
            from src.solvers.fullspace_dtn_action import _jsonable
            partial = {"status": "PARTIAL_COMPONENT_EVIDENCE", "full_case_pass": False,
                       "completed": ["532 raw coefficient/H equivalence", "per-mode all-DOF rank-one bounds",
                                     "five arbitrary-state accumulated action probes", "compiled primary/oracle Gauss binding"],
                       "pending": ["production recovery", "output component", "physical RHS", "nonzero port RHS"],
                       "physical_generator_manifest_sha256": old["mode_sha256"],
                       "assembly_mode_manifest_sha256": new_carrier.mode_manifest_sha256,
                       "assembly_context_sha256": new_carrier.assembly_context_sha256,
                       "primary_compiled_gauss": new["compiled_surface_gauss_identity"],
                       "oracle_compiled_gauss": oracle_gauss, "per_mode": ledger,
                       "probe_scope": "not a certified relative norm of the summed operator", "PDE_solved": False}
            record_path = Path(os.environ["TASK40EXTRA_GAUGE_ORACLE_RECORD"])
            record_path.with_name("partial_components.json").write_text(json.dumps(_jsonable(partial), indent=2, allow_nan=False)+"\n")
        # Verify actual primary actions against the independent accumulated
        # all-mode oracle, including arbitrary full FE states/interior DOFs.
        for bundle, label in ((old, "old_stored"), (new, "new_stored")):
            for column in range(states.shape[1]):
                source = PETSc.Vec().createSeq(n, comm=PETSc.COMM_SELF)
                target = source.duplicate()
                try:
                    source.array[:] = states[:, column]; source.assemble()
                    bundle["dtn_action"].apply(source, target)
                    assert _relative(target.array, accumulated[label][:, column]) <= 1e-10
                    recovered = bundle["dtn_action"].recover_auxiliary(source)
                    assert _relative(recovered, expected_recovery[label][:, column]) <= 1e-10
                    for index, observed in enumerate(recovered):
                        expected = expected_recovery[label][index, column]
                        scale = recovery_coefficient_scales[label][index]*np.linalg.norm(states[:, column])
                        assert abs(observed-expected) <= 1e-10*scale, (label, index, "per-entry stored recovery")
                    if label == "new_stored":
                        assert _relative(recovered, expected_recovery["plane_raw"][:, column]) <= 1e-10
                        for index, observed in enumerate(recovered):
                            expected = expected_recovery["plane_raw"][index, column]
                            scale = recovery_coefficient_scales["plane_raw"][index]*np.linalg.norm(states[:, column])
                            assert abs(observed-expected) <= 1e-10*scale, (index, "per-entry raw recovery")
                        # Lower-level consistency only: arbitrary test fields
                        # have no PDE residual/official power qualification.
                        output = prepare_boundary_plane_outputs(
                            recovered, new["incident_projections"], modes, cfg)
                        if output["status"] != "representable_global_output" and "TASK40EXTRA_GAUGE_ORACLE_RECORD" in os.environ:
                            from src.solvers.fullspace_dtn_action import _jsonable
                            failure = {"status": "FAILED_OUTPUT_COMPONENT_GATE", "full_case_pass": False,
                                       "arbitrary_state_column": column, "packet": output, "PDE_solved": False}
                            Path(os.environ["TASK40EXTRA_GAUGE_ORACLE_RECORD"]).with_name("failed_output_packet.json").write_text(
                                json.dumps(_jsonable(failure), indent=2, allow_nan=False)+"\n")
                        assert output["status"] == "representable_global_output", output.get("global_output_failure")
                        assert output["global_output_component_consistency_checked"]
                        assert output["official_results"] is False
                finally:
                    target.destroy(); source.destroy()
        old_rhs, _ = build_physical_rhs(old)
        new_rhs, _ = build_physical_rhs(new)
        try:
            assert _relative(old_rhs.array, new_rhs.array) <= 1e-10
        finally:
            old_rhs.destroy(); new_rhs.destroy()
        incident_global = np.asarray(old["incident_projections"])
        incident_plane = np.asarray(new["incident_projections"])
        np.testing.assert_allclose(solver_amplitudes_from_global(incident_global, modes, cfg, BOUNDARY_PLANE),
                                   incident_plane, rtol=1e-10, atol=1e-12)
        port_rhs_global = rng.normal(size=(532, 5)) + 1j*rng.normal(size=(532, 5))
        port_rhs_plane = plane_port_rhs_from_global(port_rhs_global, modes, cfg, BOUNDARY_PLANE)
        np.testing.assert_allclose(global_port_rhs_from_plane(port_rhs_plane, modes, cfg, BOUNDARY_PLANE),
                                   port_rhs_global, rtol=1e-10, atol=1e-12)
        if "TASK40EXTRA_GAUGE_ORACLE_RECORD" in os.environ:
            packet = {
                "scope": "532-mode all-DOF coefficient/rank-one FE action oracle; no PDE/factor/target qualification",
                "input_sha256": input_hash, "degree": 2, "azimuth_deg": 5, "mode_count": 532,
                "physical_generator_manifest_sha256": old["mode_sha256"],
                "assembly_mode_manifest_sha256": new_carrier.mode_manifest_sha256,
                "assembly_context_sha256": new_carrier.assembly_context_sha256,
                "construction_numeric_inventory": dict(new_carrier.construction_numeric_inventory),
                "primary_compiled_gauss": new["compiled_surface_gauss_identity"],
                "independent_oracle_compiled_gauss": oracle_gauss,
                "quadrature_degree": qdegree, "raw_vs_centered_action_defect": _relative(accumulated["global_raw"], accumulated["plane_raw"]),
                "new_stored_vs_raw_action_defect": _relative(accumulated["new_stored"], accumulated["plane_raw"]),
                "old_vs_new_stored_action_change": _relative(accumulated["old_stored"], accumulated["new_stored"]),
                "per_mode": ledger, "PDE_solved": False,
                "resource_authority": "external watchdog source/environment/RSS/swap/wall receipt required",
            }
            from src.solvers.fullspace_dtn_action import _jsonable
            Path(os.environ["TASK40EXTRA_GAUGE_ORACLE_RECORD"]).write_text(json.dumps(_jsonable(packet), indent=2, allow_nan=False)+"\n")
    finally:
        raw_forms.clear()
        if new is not None:
            destroy_same_mesh_physical_action(new)
        if old is not None:
            destroy_same_mesh_physical_action(old)
        levels.clear()
