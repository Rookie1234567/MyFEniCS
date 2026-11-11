"""Original-system PSTDDM comparison and explicitly diagnostic observables.

The flexible Krylov iteration checks the full uncondensed FE+auxiliary
equations at every accepted trial iterate. Diagnostic power/field recovery
does not establish mesh, modal, or target-scale physical convergence.
"""
from __future__ import annotations

import gc
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.sparse.linalg import splu


def true_residual(matrix, value, rhs):
    denominator = max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
    return float(np.linalg.norm(rhs - matrix @ value) / denominator)


def flexible_gmres(matrix, rhs, precondition, initial, *, restart=30, max_iterations=100,
                   tolerance=1e-8):
    """Right FGMRES with stored preconditioned vectors and twice-reorthogonalized MGS.

    Least squares uses the actual complex Hessenberg matrix. Neither its
    residual nor any preconditioned norm is an acceptance criterion.
    """
    if restart < 1 or max_iterations < 1 or not 0 < tolerance < 1:
        raise ValueError('invalid FGMRES controls')
    rhs = np.asarray(rhs, complex)
    x = np.asarray(initial, complex).copy()
    if rhs.ndim != 1 or x.shape != rhs.shape:
        raise ValueError('FGMRES vector layout mismatch')
    scale = max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
    residual = rhs-matrix@x
    history = [{'iteration': 0, 'true_residual': float(np.linalg.norm(residual)/scale)}]
    start = perf_counter()
    pc_seconds = 0.0
    iterations = 0
    reason = 'maximum_iterations'
    while iterations < max_iterations:
        beta = float(np.linalg.norm(residual))
        if beta/scale <= tolerance:
            reason = 'converged'
            break
        width = min(restart, max_iterations-iterations)
        V = np.zeros((rhs.size, width+1), complex)
        Z = np.zeros((rhs.size, width), complex)
        H = np.zeros((width+1, width), complex)
        V[:, 0] = residual/beta
        old = x.copy()
        cycle_breakdown = False
        for j in range(width):
            tick = perf_counter()
            z = np.asarray(precondition(V[:, j].copy()), complex)
            pc_seconds += perf_counter()-tick
            if z.shape != rhs.shape or not np.isfinite(z).all():
                raise FloatingPointError('nonfinite or incompatible flexible PC output')
            Z[:, j] = z
            w = np.asarray(matrix@z, complex)
            original_norm = float(np.linalg.norm(w))
            for _ in range(2):
                for k in range(j+1):
                    coefficient = np.vdot(V[:, k], w)
                    H[k, j] += coefficient
                    w -= coefficient*V[:, k]
            H[j+1, j] = np.linalg.norm(w)
            cycle_breakdown = abs(H[j+1, j]) <= np.finfo(float).eps*max(1., original_norm)*32
            if not cycle_breakdown:
                V[:, j+1] = w/H[j+1, j]
            projected_rhs = np.zeros(j+2, complex)
            projected_rhs[0] = beta
            coefficients = np.linalg.lstsq(H[:j+2, :j+1], projected_rhs, rcond=None)[0]
            x = old + Z[:, :j+1]@coefficients
            residual = rhs-matrix@x
            iterations += 1
            relative = float(np.linalg.norm(residual)/scale)
            if not np.isfinite(relative):
                raise FloatingPointError('nonfinite original-system FGMRES residual')
            history.append({'iteration': iterations, 'true_residual': relative})
            if relative <= tolerance:
                reason = 'converged'
                break
            if cycle_breakdown:
                reason = 'arnoldi_breakdown_without_true_residual_pass'
                break
        if reason == 'converged' or cycle_breakdown:
            break
    final = true_residual(matrix, x, rhs)
    return x, {'algorithm': 'flexible_right_GMRES_two_pass_MGS', 'restart': restart,
               'maximum_iterations': max_iterations, 'iterations': iterations,
               'reason': reason, 'true_residual': final, 'history': history,
               'wall_seconds': perf_counter()-start, 'pc_apply_seconds': pc_seconds,
               'passed': final <= tolerance}


def _real_nonnegative(value, name):
    result = float(np.real(value))
    if not np.isfinite(result) or result < -1e-10:
        raise FloatingPointError(f'invalid {name}: {value}')
    return max(result, 0.)


def background_norm_payload(system):
    """Saveable exact FE couplings to the analytic background, quadrature 28.

    m_bg[j]=integral(bg dot conjugate(phi_j)); k_bg uses both curls.
    Consequently ||FE(e)+bg||^2=e^H M e+2 Re(e^H m_bg)+||bg||^2.
    These are dual vectors in the same projected Floquet layout as system.M.
    """
    import ufl
    from dolfinx import fem
    from dolfinx.fem import petsc as fp
    from petsc4py import PETSc
    from .pstddm_native import scalar

    cached = getattr(system, '_pstddm_background_norm_payload', None)
    if cached is not None:
        return cached
    p = system.p
    v = ufl.TestFunction(p.V)
    bg = p.analytic_Ebg

    def load(expression):
        compiled = fem.form(expression, jit_options={'cache_dir': str(system.cache), 'timeout': 300},
                            form_compiler_options={'quadrature_degree': 28})
        vector = fp.assemble_vector(compiled)
        vector.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
        projected = np.asarray(system.T.conj().T@vector.array_r).copy()
        vector.destroy()
        return projected

    payload = {'m_bg': load(ufl.inner(bg, v)*ufl.dx),
               'k_bg': load(ufl.inner(ufl.curl(bg), ufl.curl(v))*ufl.dx),
               'background_E_l2_squared': _real_nonnegative(
                   scalar(ufl.inner(bg, bg)*ufl.dx, system.cache), 'background E norm'),
               'background_curl_l2_squared': _real_nonnegative(
                   scalar(ufl.inner(ufl.curl(bg), ufl.curl(bg))*ufl.dx, system.cache),
                   'background curl norm'),
               'H_curl_norm_divisor': abs(p.cfg.k0*complex(p.cfg.mu_r))**2,
               'quadrature_degree': 28}
    system._pstddm_background_norm_payload = payload
    return payload


def reconstruct_field_norms(system, e, payload):
    """Matrix/vector-only total and scattered squared norms for offline review."""
    electric = _real_nonnegative(np.vdot(e, system.M@e), 'scattered E norm')
    curl = _real_nonnegative(np.vdot(e, system.K@e), 'scattered curl norm')
    total_e = _real_nonnegative(electric + 2*np.real(np.vdot(e, payload['m_bg']))
                               + payload['background_E_l2_squared'], 'total E norm')
    total_curl = _real_nonnegative(curl + 2*np.real(np.vdot(e, payload['k_bg']))
                                  + payload['background_curl_l2_squared'], 'total curl norm')
    divisor = float(payload['H_curl_norm_divisor'])
    return {'E_total_l2_squared': total_e, 'H_total_l2_squared': total_curl/divisor,
            'E_scattered_l2_squared': electric, 'H_scattered_l2_squared': curl/divisor}


def diagnostic_observables(system, z, out, prefix):
    """Exact-UFL field integrals and boundary-plane mode power diagnostics.

    Saved magnetic coefficients are a DG interpolation and are labelled as
    such. The H norm below integrates curl(Etotal)/(i*k0*mu), not the DG field.
    """
    import ufl
    from dolfinx import fem
    from .pstddm_native import scalar
    from src.common.analytic_fields_3d import _fresnel_components
    from src.common.modes_3d import incident_power_3d

    out = Path(out)
    p, cfg = system.p, system.p.cfg
    n = system.A.shape[0]
    e, q = np.asarray(z[:n]), np.asarray(z[n:])
    scattered = fem.Function(p.V)
    scattered.x.array[:] = system.T@e
    scattered.x.scatter_forward()
    electric = scattered+p.analytic_Ebg
    magnetic = ufl.curl(electric)/(1j*cfg.k0*complex(cfg.mu_r))
    dx = ufl.Measure('dx', domain=p.V.mesh, subdomain_data=p.mesh_data.cell_tags)
    e_norm = _real_nonnegative(scalar(ufl.inner(electric, electric)*ufl.dx,
                                      system.cache), 'total E squared L2')
    h_norm = _real_nonnegative(scalar(ufl.inner(magnetic, magnetic)*ufl.dx,
                                      system.cache), 'total H squared L2')
    payload = background_norm_payload(system)
    reconstructed_norms = reconstruct_field_norms(system, e, payload)
    norm_defects = {
        'E': abs(reconstructed_norms['E_total_l2_squared']-e_norm)/max(e_norm, np.finfo(float).tiny),
        'H': abs(reconstructed_norms['H_total_l2_squared']-h_norm)/max(h_norm, np.finfo(float).tiny)}
    if max(norm_defects.values()) > 1e-10:
        raise RuntimeError(f'background cross-vector norm identity failed: {norm_defects}')
    incident = float(incident_power_3d(cfg))
    epsilon = {int(cfg.tags.air): complex(cfg.eps_r),
               int(cfg.tags.substrate): complex(cfg.substrate_index**2),
               int(cfg.tags.grating): complex(cfg.grating_index**2)}
    volume_by_tag = {}
    for tag, eps in epsilon.items():
        integral = _real_nonnegative(scalar(ufl.inner(electric, electric)*dx(tag),
                                             system.cache), 'material electric integral')
        volume_by_tag[str(tag)] = cfg.k0*.5*eps.imag*integral/incident
    _, kr, kt, _, er, et = _fresnel_components(cfg)
    mode_records = []
    reflection = transmission = 0.
    for j, mode in enumerate(system.dtn.modes):
        amplitude = complex(q[j])
        if mode.m == 0 and mode.n == 0:
            k, background = (kr, er) if mode.side == 'top' else (kt, et)
            boundary = cfg.physical_z_max if mode.side == 'top' else cfg.physical_z_min
            boundary_field = background*np.exp(1j*k[2]*boundary)
            amplitude += np.vdot(mode.e_vector[:2], boundary_field[:2])/mode.electric_tangential_norm_sq
        power = float(mode.power_per_unit_amplitude*abs(amplitude)**2/incident)
        if mode.side == 'top':
            reflection += power
        else:
            transmission += power
        mode_records.append({'side': mode.side, 'm': int(mode.m), 'n': int(mode.n),
                             'polarization': mode.polarization,
                             'amplitude': [amplitude.real, amplitude.imag],
                             'normalized_power': power,
                             'propagating': bool(mode.propagating)})
    # Cell-discontinuous magnetic values preserve jumps at material interfaces.
    Hspace = fem.functionspace(p.V.mesh, ('DG', int(cfg.nedelec_degree), (3,)))
    H = fem.Function(Hspace)
    points = Hspace.element.interpolation_points
    points = points() if callable(points) else points
    expression = fem.Expression(magnetic, points, jit_options={'cache_dir': str(system.cache),
                                                              'timeout': 300})
    H.interpolate(expression)
    np.savez(out/f'{prefix}_fields.npz', scattered_E_original=np.asarray(scattered.x.array),
             scattered_E_independent=e, **payload,
             H_DG_interpolated=np.asarray(H.x.array),
             H_DG_dof_coordinates=Hspace.tabulate_dof_coordinates(),
             H_DG_cell_dofs=np.asarray([Hspace.dofmap.cell_dofs(i) for i in
                                       range(p.V.mesh.topology.index_map(3).size_local)]))
    absorption = float(sum(volume_by_tag.values()))
    result = {'qualification': 'diagnostic_unqualified_for_physical_convergence',
              'field_definition': 'total E = scattered FE E + analytic flat-interface background',
              'H_definition': 'code units curl(Etotal)/(i*k0*mu_r)',
              'saved_H_representation': 'vector DG interpolation; not used for the H error integral',
              'E_total_l2_squared': e_norm, 'H_total_l2_squared': h_norm,
              'E_scattered_l2_squared': reconstructed_norms['E_scattered_l2_squared'],
              'H_scattered_l2_squared': reconstructed_norms['H_scattered_l2_squared'],
              'offline_reconstructed_norms': reconstructed_norms,
              'background_cross_vector_identity_relative_defects': norm_defects,
              'background_payload_file': f'{prefix}_fields.npz',
              'background_payload_identity': 'm_bg=T^H integral(bg dot conj(v)); k_bg=T^H integral(curl(bg) dot conj(curl(v))); quadrature28',
              'incident_power': incident, 'R_total': float(reflection),
              'T_total': float(transmission), 'A_flux': float(1.-reflection-transmission),
              'A_volume': absorption, 'volume_absorption_by_material_tag': volume_by_tag,
              'energy_defect': float(reflection+transmission+absorption-1.),
              'mode_gauge': 'boundary_plane', 'modes': mode_records}
    (out/f'{prefix}_diagnostics.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


def direct_reference(system, gate, out):
    """Independent full augmented direct reference; factor released before recovery."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    gate('direct_reference_factor', 4*system.full.shape[0]**2*16)
    tick = perf_counter()
    factor = splu(system.full.tocsc())
    factor_seconds = perf_counter()-tick
    factor_nnz = int(factor.L.nnz+factor.U.nnz)
    tick = perf_counter()
    z = factor.solve(system.rhs)
    solve_seconds = perf_counter()-tick
    del factor
    gc.collect()
    residual = true_residual(system.full, z, system.rhs)
    np.savez(out/'reference_solution.npz', z=z)
    if not np.isfinite(residual) or residual > 1e-10:
        raise RuntimeError(f'direct original FE+aux residual failed: {residual}')
    gate('direct_reference_diagnostics', 256 << 20)
    tick = perf_counter()
    diagnostics = diagnostic_observables(system, z, out, 'reference')
    return {'z': z, 'true_residual': residual, 'factor_seconds': factor_seconds,
            'solve_seconds': solve_seconds, 'factor_nnz': factor_nnz,
            'recovery_seconds': perf_counter()-tick, 'diagnostics': diagnostics}


def candidate(system, core, reference, out):
    """Single source-transfer initial guess followed, if needed, by FGMRES."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    n = system.A.shape[0]
    applies = []

    def precondition(residual):
        e = core(residual[:n]-system.C@residual[n:])
        q = residual[n:]-system.D@e
        if core.last_statistics is not None:
            applies.append(core.last_statistics.copy())
        return np.r_[e, q]

    tick = perf_counter()
    x0 = precondition(system.rhs)
    first_seconds = perf_counter()-tick
    first_residual = true_residual(system.full, x0, system.rhs)
    z, iteration = flexible_gmres(system.full, system.rhs, precondition, x0,
                                  restart=30, max_iterations=100, tolerance=1e-8)
    np.savez(out/'candidate_solution.npz', z=z, x0=x0)
    tick = perf_counter()
    diagnostics = diagnostic_observables(system, z, out, 'candidate')
    refdiag = reference['diagnostics']

    def errors(value):
        delta = value[:n]-reference['z'][:n]
        e2 = _real_nonnegative(np.vdot(delta, system.M@delta), 'E error norm')
        h2 = _real_nonnegative(np.vdot(delta, system.K@delta), 'curl error norm')
        h2 /= abs(system.p.cfg.k0*complex(system.p.cfg.mu_r))**2
        norms = reconstruct_field_norms(system, value[:n], background_norm_payload(system))
        return {'E_relative_L2': float(np.sqrt(e2/max(refdiag['E_total_l2_squared'], np.finfo(float).tiny))),
                'H_relative_L2': float(np.sqrt(h2/max(refdiag['H_total_l2_squared'], np.finfo(float).tiny))),
                'E_scattered_relative_L2': float(np.sqrt(e2/max(refdiag['E_scattered_l2_squared'], np.finfo(float).tiny))),
                'H_scattered_relative_L2': float(np.sqrt(h2/max(refdiag['H_scattered_l2_squared'], np.finfo(float).tiny))),
                'E_error_l2_squared': e2, 'H_error_l2_squared': h2,
                'field_squared_norms': norms}

    initial_errors, final_errors = errors(x0), errors(z)
    differences = {key: abs(diagnostics[key]-refdiag[key]) for key in
                   ['R_total', 'T_total', 'A_flux', 'A_volume', 'energy_defect']}
    mode_differences = []
    for actual, expected in zip(diagnostics['modes'], refdiag['modes'], strict=True):
        if tuple(actual[k] for k in ['side', 'm', 'n', 'polarization']) != tuple(
                expected[k] for k in ['side', 'm', 'n', 'polarization']):
            raise RuntimeError('candidate and reference modal order differs')
        mode_differences.append(abs(actual['normalized_power']-expected['normalized_power']))
    differences['maximum_individual_mode_power'] = max(mode_differences, default=0.)
    solver_pass = (iteration['true_residual'] <= 1e-8 and final_errors['E_relative_L2'] <= 1e-4
                   and final_errors['H_relative_L2'] <= 1e-3)
    return {'z': z, 'initial_true_residual': first_residual, 'initial_errors': initial_errors,
            'first_double_sweep_seconds': first_seconds,
            'final_true_residual': iteration['true_residual'], 'field_errors': final_errors,
            'FGMRES': iteration, 'pc_applications': applies,
            'recovery_seconds': perf_counter()-tick, 'diagnostics': diagnostics,
            'diagnostic_absolute_differences': differences,
            'same_discrete_solver_pass': bool(solver_pass),
            'diagnostic_H_comparison_pass': final_errors['H_relative_L2'] <= 1e-3,
            'diagnostic_power_comparison_pass': max(differences.values()) <= 1e-4,
            'physical_convergence_qualified': False}
