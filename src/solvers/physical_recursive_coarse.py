"""Bounded right FGMRES for the physical p4 equation; no reference data inputs."""
import numpy as np
from .fullspace_physical_intermediate import apply_owned


def solve_physical_i4(rhs, action, pc, *, target, sample, save, clock=None, stop_requested=lambda: False,
                      residual_norm=None):
    """One zero-start FGMRES16/max64; owned solution, A4c and eps returned.

    Each monitor boundary checks the conservative 60-second clock. The terminal
    explicit residual is authoritative even after a finite iteration/time cap.
    """
    from petsc4py import PETSc
    from .fullspace_memory_first_krylov import _ActionContext, _PCContext
    from src.runners.workflow_timebase import ClockBudget, clock_sample, CONSERVATIVE_REALTIME
    if target not in (1e-4, 1e-6):
        raise ValueError('I4 target must be LO=1e-4 or HI=1e-6')
    budget = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
    seconds = clock or (lambda: budget.update(clock_sample())['budget_seconds'])
    attempted = dict(A4_matvec=0, B4_calls=0, explicit_A4=0)
    def counted_action(x):
        attempted['A4_matvec'] += 1
        return action(x)
    def counted_pc(x):
        attempted['B4_calls'] += 1
        return pc(x)
    ac, context = _ActionContext(counted_action), _PCContext(counted_pc)
    sizes = (rhs.getLocalSize(), rhs.getSize())
    matrix = PETSc.Mat().createPython((sizes, sizes), context=ac, comm=rhs.getComm())
    matrix.setUp()
    x, current = rhs.duplicate(), rhs.duplicate(); x.set(0); current.set(0)
    ksp = applied = eps = None
    history = []; explicit_count = 0; status = None
    norm = float(rhs.norm()) if residual_norm is None else float(residual_norm)
    def explicit(value, iteration, *, retain=False):
        nonlocal explicit_count
        attempted['explicit_A4'] += 1
        a = action(value); r = rhs.copy()
        try:
            r.axpy(-1, a); absolute = float(r.norm())
            relative = absolute/norm if norm else (0. if absolute == 0 else float('inf'))
            if not np.isfinite(relative):
                raise FloatingPointError('nonfinite original A4 residual')
            explicit_count += 1
            history.append(dict(iteration=iteration, absolute=absolute, relative=relative, seconds=seconds()))
            if retain:
                kept = (relative, a, r); a = r = None; return kept
            return relative
        finally:
            if a is not None: a.destroy()
            if r is not None: r.destroy()
    try:
        if not np.isfinite(norm) or norm<0:
            raise FloatingPointError('nonfinite p4 RHS')
        ksp = PETSc.KSP().create(rhs.getComm()); ksp.setOperators(matrix)
        ksp.setType('fgmres'); ksp.setGMRESRestart(16); ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED); ksp.setInitialGuessNonzero(False)
        ksp.setTolerances(rtol=0., atol=0., max_it=64)
        ksp.getPC().setType('python'); ksp.getPC().setPythonContext(context)
        def convergence(solver, it, reported):
            nonlocal status
            sample(); now = seconds()
            if not np.isfinite(reported):
                raise FloatingPointError('nonfinite inner reported residual')
            cap = now >= 60 or it >= 64 or stop_requested()
            if it % 16 == 0 or cap or reported <= target*norm:
                if it: solver.buildSolution(current)
                else: current.set(0)
                relative = explicit(current, int(it))
                if relative <= target:
                    status = 'INNER_TARGET_REACHED'
                    return int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL)
                if cap:
                    status = 'INNER_INEXACT_AT_CAP'
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
            return 0
        ksp.setConvergenceTest(convergence)
        ksp.solve(rhs, x)
        iterations, reason = int(ksp.getIterationNumber()), int(ksp.getConvergedReason())
        relative, applied, eps = explicit(x, iterations, retain=True)
        # FGMRES Arnoldi rank saturation can be finite without solving the RHS.
        # This is distinct from NaN/Inf, PC failure, or unrelated solver failures.
        finite_reasons = (int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT),
                          int(PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN))
        if reason < 0 and reason not in finite_reasons:
            raise RuntimeError(f'inner breakdown reason={reason}, true={relative}')
        status = 'INNER_TARGET_REACHED' if relative <= target else 'INNER_INEXACT_AT_CAP'
        facts = dict(status=status, target=target, final_true_residual=relative,
            eps_norm=float(eps.norm()), rhs_norm=norm, iterations=iterations, reason=reason,
            restart=16, max_it=64, zero_start=True, seconds=seconds(), history=history,
            A4_matvec=ac.matvec_count, B4_calls=context.apply_count,
            explicit_A4=explicit_count, attempted=dict(attempted), inner_basis_payload_bound=33*rhs.getSize()*16,
            basis_payload_classification='derived V/Z bound, excludes work vectors and allocator',
            ksp_create_count=1, ksp_solve_count=1, ksp_destroy_count=0,
            finite_arnoldi_saturation=reason == int(PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN))
        ksp.destroy(); ksp = None; facts['ksp_destroy_count'] = 1
        result = dict(solution=x, applied=applied, residual=eps, facts=facts)
        x = applied = eps = None
        return result
    except BaseException as exc:
        try:
            elapsed = seconds()
        except BaseException:
            elapsed = None  # preserve the primary failure if the clock itself is invalid
        save('inner_failure', dict(rhs=rhs.array.copy(), last_safe=current.array.copy(), terminal=x.array.copy(),
            history=history, reason=str(exc), A4_matvec=ac.matvec_count, B4_calls=context.apply_count,
            explicit_A4=explicit_count, iterations=int(ksp.getIterationNumber()) if ksp is not None else 0,
            conservative_seconds=elapsed, attempted=dict(attempted),
            call_count_semantics='A4_matvec/B4_calls/explicit_A4 are completed; attempted includes failed boundary' ))
        raise
    finally:
        for value in (eps, applied, current, x):
            if value is not None: value.destroy()
        if ksp is not None: ksp.destroy()
        matrix.destroy()


class PhysicalP2Inverse:
    """One bounded augmented factor; native A2 residual, at most two refinements."""
    def __init__(self, matrix, action, slaves, *, sample, marker, save):
        from .fullspace_bounded_mumps import BoundedP1Factor
        self.bottom = BoundedP1Factor(matrix, label='physical_p2', resource_sample=sample,
            marker=marker, physical_p2_pilot=True)
        self.matrix, self.action = matrix, action
        self.slaves, self.sample, self.save = np.asarray(slaves, dtype=int), sample, save
        self.counts = dict(logical=0, MatSolve_attempted=0, MatSolve=0, refinement=0, A2_true=0)
        self.last_facts = {}

    def apply(self, rhs):
        start = dict(self.counts)
        self.counts['logical'] += 1
        x = rhs.duplicate(); x.set(0)
        residual = rhs.copy(); augmented = self.matrix.createVecRight()
        correction = applied = None
        try:
            if not np.isfinite(rhs.norm()) or np.any(rhs.array[self.slaves] != 0):
                raise ValueError('illegal p2 dual RHS')
            norm = float(rhs.norm())
            for refinement in range(3):
                self.sample(); augmented.set(0); augmented.array[:rhs.getLocalSize()] = residual.array
                self.counts['MatSolve_attempted'] = self.counts.get('MatSolve_attempted', 0)+1
                correction, _ = self.bottom.solve_lean(augmented)
                self.counts['MatSolve'] += 1
                if refinement: self.counts['refinement'] += 1
                x.array[:] += correction.array[:rhs.getLocalSize()]
                correction.destroy(); correction = None
                if not np.isfinite(x.norm()) or np.max(np.abs(x.array[self.slaves]), initial=0) > 1e-12:
                    raise ValueError('p2 solution has nonfinite/slave contamination')
                x.array[self.slaves] = 0
                applied = apply_owned(self.action, x); self.counts['A2_true'] += 1
                rhs.copy(residual); residual.axpy(-1, applied); applied.destroy(); applied = None
                relative = float(residual.norm()/norm) if norm else float(residual.norm())
                self.last_facts = dict(relative=relative, refinement=refinement,
                    counts={k:v-start.get(k,0) for k,v in self.counts.items()})
                if np.isfinite(relative) and relative <= 1e-10:
                    value=x; x=None; return value
            raise RuntimeError('native A2 residual exceeds 1e-10 after two refinements')
        except BaseException as exc:
            self.save('bottom_failure', dict(rhs=rhs.array.copy(), solution=x.array.copy(), residual=residual.array.copy(),
                facts=self.last_facts, counts_since_start={k:v-start.get(k,0) for k,v in self.counts.items()},
                MatSolve_semantics='attempted includes failure; MatSolve counts completed', reason=str(exc)))
            raise
        finally:
            for value in (correction, applied, augmented, residual, x):
                if value is not None: value.destroy()

    def destroy(self):
        self.bottom.destroy()


def build_recursive_physical_solver(cfg, comm, *, target, sample, marker, save, audit_every=32, observe_inner=None, stop_requested=lambda: False):
    """Explicit 6/4/2 pilot. No p4 reference=True path and no unused shifted levels."""
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action
    from .fullspace_physical_intermediate_runtime import build_physical_intermediate_actions, owned_slave_indices
    from .physical_light_setup import build_light_h6_setup, build_light_level_setup
    from .fullspace_p4_reference import build_reference_matrix
    from .physical_balanced_coupling import PhysicalBalancedCoupling
    from .physical_inexact_balance import InexactBalanceLedger
    bundle = dict(profile='recursive_physical_p4', target=target, inner_records=[],
        counts=dict(I4=0, B4=0, A4_matvec=0, explicit_A4=0, H4=0, H4_positive=0, H6=0, H6_positive=0),
        numerical_storage=dict(levels=[6,4,2], p6_global_aij=0, p4_global_aij=0,
            p6_global_factor=0, p4_global_factor=0, bottom='bounded_physical_p2'))
    try:
        sample(); levels = _build_same_mesh_levels(cfg, comm, (6,4,2)); bundle['levels'] = levels
        bundle['positive'] = build_light_h6_setup(levels, cfg, marker)
        fine = build_same_mesh_physical_action(levels, cfg, 6); bundle['fine'] = fine
        actions = build_physical_intermediate_actions(levels, cfg, fine_bundle=fine,
            stage_callback=marker, physical_only_degrees=(6,4,2)); bundle['actions'] = actions
        bundle['h4_setup'] = build_light_level_setup(levels, cfg, marker, degree=4)
        sample()
        matrix, facts = build_reference_matrix(levels, cfg, actions['physical'][2],
            actions['volume_quadrature_metadata'], marker=marker, sample=sample, degree=2, row_cap=8192)
        bundle['p2_matrix'], bundle['p2_matrix_facts'] = matrix, facts
        bottom = PhysicalP2Inverse(matrix, actions['physical'][2]['physical_action'],
            owned_slave_indices(levels['spaces'][2], levels['floquets'][2]), sample=sample, marker=marker, save=save)
        bundle['p2_inverse'] = bottom
        p42, p64 = actions['transfers'][(4,2)], actions['transfers'][(6,4)]
        def a4(x): return apply_owned(actions['physical'][4]['physical_action'], x)
        def a6(x): return apply_owned(fine['physical_action'], x)
        def c42(x):
            rhs = p42.apply_adjoint(x); y = None
            try:
                y = bottom.apply(rhs); return p42.apply_primal(y)
            finally:
                rhs.destroy()
                if y is not None: y.destroy()
        def h4(x):
            smoother = bundle['h4_setup']['smoother']
            value = smoother.apply(x)
            bundle['counts']['H4'] += 1
            bundle['counts']['H4_positive'] += smoother.last_apply_facts['matrix_mult_count']
            return value
        b4 = PhysicalBalancedCoupling(a4, c42, h4, p42.apply_adjoint, route='BAL_H',
            checkpoint=sample, level_identity='p4/p2 exact physical bottom')
        bundle['B4'] = b4
        def apply_b4(x):
            value = b4.apply(x); bundle['counts']['B4'] += 1
            for key, elapsed in b4.last_apply_facts['operation_seconds'].items():
                name = 'B4_'+key+'_seconds'
                bundle['counts'][name] = bundle['counts'].get(name, 0.)+elapsed
            for key, count in b4.last_apply_facts['counts'].items():
                name = 'B4_'+key
                bundle['counts'][name] = bundle['counts'].get(name, 0)+count
            return value
        def i4(rhs):
            before = dict(bottom.counts)
            bundle['counts']['I4'] += 1
            def failed(name, row):
                for key in ('A4_matvec', 'explicit_A4'):
                    bundle['counts'][key] += row[key]
                bundle['counts']['I4_failed'] = bundle['counts'].get('I4_failed',0)+1
                row['incomplete_callbacks'] = {key:value-row[key] for key,value in row['attempted'].items()}
                row['p2_counts'] = {k:v-before.get(k,0) for k,v in bottom.counts.items()}
                save(name,row)
            result = solve_physical_i4(rhs, a4, apply_b4, target=target, sample=sample, save=failed, stop_requested=stop_requested)
            for key in ('A4_matvec', 'explicit_A4'):
                bundle['counts'][key] += result['facts'][key]
            result['facts']['p2_counts'] = {k:v-before[k] for k,v in bottom.counts.items()}
            if observe_inner is not None:
                try:
                    observe_inner(rhs, result)
                except BaseException:
                    for key in ('solution', 'applied', 'residual'):
                        result[key].destroy()
                    raise
            # Last record only; callers persist ordinary scalar summaries as needed.
            bundle['inner_records'][:] = [result['facts']]
            marker('I4_complete', result['facts'])
            return result
        ledger = InexactBalanceLedger(a6, p64.apply_adjoint, save=save, checkpoint=sample, every=audit_every)
        bundle['inexact_ledger'] = ledger
        def c64(x):
            g = p64.apply_adjoint(x); result = None
            try:
                result = i4(g)
                ledger.record(g, result['applied'], result['residual'], result['facts'])
                return p64.apply_primal(result['solution'])
            finally:
                g.destroy()
                if result:
                    for key in ('solution','applied','residual'): result[key].destroy()
        def h6(x):
            smoother = bundle['positive']['h6']; value = smoother.apply(x)
            bundle['counts']['H6'] += 1
            bundle['counts']['H6_positive'] += smoother.last_apply_facts['matrix_mult_count']
            return value
        bundle['I4'] = i4
        bundle['pc'] = PhysicalBalancedCoupling(a6, c64, h6, p64.apply_adjoint, route='BAL_H',
            checkpoint=sample, inexact_ledger=ledger, level_identity='p6/p4 inexact physical I4')
        return bundle
    except BaseException:
        destroy_recursive_physical_solver(bundle)
        raise


def release_recursive_physical_solver_stack(bundle):
    from .fullspace_physical_intermediate_runtime import destroy_physical_intermediate_actions
    # Drop closures before releasing their borrowed coarse objects. Fine remains for recovery.
    for name in ('I4', 'B4', 'pc'):
        bundle.pop(name, None)
    for name in ('inexact_ledger', 'p2_inverse', 'p2_matrix'):
        value = bundle.pop(name, None)
        if value is not None: value.destroy()
    for name in ('h4_setup', 'positive'):
        value = bundle.pop(name, None)
        if value is not None:
            if name == 'positive':
                value['h6'].destroy(); value['p6_shell'].destroy()
            else:
                value['smoother'].destroy(); value['shell'].destroy()
    value = bundle.pop('actions', None)
    if value is not None: destroy_physical_intermediate_actions(value)
    bundle['auxiliary_stack_released'] = True


def destroy_recursive_physical_solver(bundle):
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    release_recursive_physical_solver_stack(bundle)
    value = bundle.pop('fine', None)
    if value is not None: destroy_same_mesh_physical_action(value)
    bundle.clear()
