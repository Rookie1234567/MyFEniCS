"""Bounded right FGMRES for the physical p4 equation; no reference data inputs."""
import numpy as np
from .fullspace_physical_intermediate import apply_owned


def solve_physical_i4(rhs, action, pc, *, target, sample, save, clock=None, stop_requested=lambda: False,
                      residual_norm=None, residual_action=None, pc_observer=None,
                      max_it=64, restart=16,
                      soft_seconds=60, hard_seconds=None, v7_policy=False, macro_policy=False):
    """One zero-start FGMRES16 with an opt-in finite V7 policy.

    The historical default remains max64/60 seconds.  V7 passes
    ``max_it=16, soft_seconds=25, hard_seconds=30, v7_policy=True``; that
    policy changes only the cap/ledger semantics and reuses this KSP,
    explicit-residual, and cleanup implementation.
    """
    from petsc4py import PETSc
    from .fullspace_memory_first_krylov import _ActionContext, _PCContext
    from src.runners.workflow_timebase import ClockBudget, clock_sample, CONSERVATIVE_REALTIME
    if target not in (1e-4, 1e-6):
        raise ValueError('I4 target must be LO=1e-4 or HI=1e-6')
    if macro_policy:
        if target != 1e-4 or int(restart) != 4 or int(max_it) != 4:
            raise ValueError('Review V10 macro I4 fixes target=1e-4, restart=4, max_it=4')
    elif int(restart) != 16 or int(max_it) <= 0:
        raise ValueError('I4 restart must be 16 and max_it must be positive')
    if not np.isfinite(soft_seconds) or soft_seconds <= 0:
        raise ValueError('I4 soft time limit must be finite and positive')
    if hard_seconds is not None and (not np.isfinite(hard_seconds) or hard_seconds < soft_seconds):
        raise ValueError('I4 hard time limit must be finite and no shorter than soft limit')
    if v7_policy and (target != 1e-4 or int(max_it) != 16 or float(soft_seconds) != 25.0 or
                      hard_seconds is None or float(hard_seconds) != 30.0):
        raise ValueError('V7 I4 fixes target=1e-4, max_it=16, soft=25, hard=30')
    if macro_policy and (float(soft_seconds) != 25.0 or hard_seconds is None or float(hard_seconds) != 30.0):
        raise ValueError('Review V10 macro I4 fixes soft=25 and hard=30 seconds')
    bounded_policy = bool(v7_policy or macro_policy)
    budget = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
    seconds = clock or (lambda: budget.update(clock_sample())['budget_seconds'])
    raw_rhs_norm = float(rhs.norm())
    if bounded_policy and raw_rhs_norm == 0.0:
        solution = rhs.duplicate(); applied = rhs.duplicate(); eps = rhs.duplicate()
        solution.set(0); applied.set(0); eps.set(0)
        facts = dict(status='INNER_ZERO_RHS', quality_label='ZERO_RHS', target=target,
            final_true_residual=0., residual_absolute=0., rhs_norm=0., iterations=0,
            reason=0, restart=restart, max_it=max_it, zero_start=True,
            seconds=seconds(), actual_elapsed_seconds=seconds(), requested_safe_return=False,
            timeout_exceeded=False, stop_reason='ZERO_RHS', legal_direction_count=0,
            A4_matvec=0, B4_calls=0, explicit_A4=0, attempted=dict(A4_matvec=0, B4_calls=0, explicit_A4=0),
            ksp_create_count=0, ksp_solve_count=0, ksp_destroy_count=0,
            explicit_uses_separate_action=residual_action is not None)
        return dict(solution=solution, applied=applied, residual=eps, facts=facts)
    attempted = dict(A4_matvec=0, B4_calls=0, explicit_A4=0)
    legal_direction_count = 0
    def counted_action(x):
        attempted['A4_matvec'] += 1
        return action(x)
    def counted_pc(x):
        nonlocal legal_direction_count
        attempted['B4_calls'] += 1
        value = pc(x)
        if pc_observer is not None and value is not None:
            # The KSP owns ``value`` and may reuse it immediately.  The
            # observer receives independent NumPy copies and cannot change
            # the production action or PETSc work-vector lifetime.
            pc_observer(
                np.array(x.array, dtype=np.complex128, copy=True),
                np.array(value.array, dtype=np.complex128, copy=True),
                int(attempted['B4_calls']),
            )
        if bounded_policy and value is not None:
            try:
                value_norm = float(value.norm())
            except AttributeError:
                value_norm = float(np.linalg.norm(value.array))
            if np.isfinite(value_norm) and value_norm > 0.0:
                legal_direction_count += 1
        return value
    ac, context = _ActionContext(counted_action), _PCContext(counted_pc)
    sizes = (rhs.getLocalSize(), rhs.getSize())
    matrix = PETSc.Mat().createPython((sizes, sizes), context=ac, comm=rhs.getComm())
    matrix.setUp()
    x, current = rhs.duplicate(), rhs.duplicate(); x.set(0); current.set(0)
    ksp = applied = eps = None
    history = []; explicit_count = 0; status = None
    requested_safe_return = False; timeout_exceeded = False; stop_reason = None
    norm = raw_rhs_norm if residual_norm is None else float(residual_norm)
    def explicit(value, iteration, *, retain=False):
        nonlocal explicit_count
        attempted['explicit_A4'] += 1
        a = r = None
        a = (action if residual_action is None else residual_action)(value); r = rhs.copy()
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
        ksp.setType('fgmres'); ksp.setGMRESRestart(restart); ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED); ksp.setInitialGuessNonzero(False)
        ksp.setTolerances(rtol=0., atol=0., max_it=max_it)
        ksp.getPC().setType('python'); ksp.getPC().setPythonContext(context)
        def convergence(solver, it, reported):
            nonlocal status, requested_safe_return, timeout_exceeded, stop_reason
            sample(); now = seconds()
            if not np.isfinite(reported):
                raise FloatingPointError('nonfinite inner reported residual')
            outer_stop = bool(stop_requested())
            soft = now >= soft_seconds
            hard = hard_seconds is not None and now >= hard_seconds
            if outer_stop or soft:
                requested_safe_return = True
                stop_reason = 'OUTER_SAFE_DEADLINE' if outer_stop else 'I4_SAFE_RETURN_REQUESTED'
            if hard:
                timeout_exceeded = True
                stop_reason = 'I4_HARD_TIME_EXCEEDED'
            cap = hard or soft or it >= max_it or outer_stop
            # A reported residual is only a trigger for an explicit native
            # check.  A failed native check before the cap must continue.
            if it % 16 == 0 or cap or reported <= target*norm:
                if it: solver.buildSolution(current)
                else: current.set(0)
                relative = explicit(current, int(it))
                if relative <= target:
                    status = 'INNER_TARGET_REACHED'
                    return int(PETSc.KSP.ConvergedReason.CONVERGED_RTOL)
                if cap:
                    status = 'INNER_APPROXIMATE_RETURN' if bounded_policy else 'INNER_INEXACT_AT_CAP'
                    if stop_reason is None: stop_reason = 'MAX_IT' if it >= max_it else 'I4_SAFE_RETURN_REQUESTED'
                    return int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT)
            return 0
        ksp.setConvergenceTest(convergence)
        ksp.solve(rhs, x)
        iterations, reason = int(ksp.getIterationNumber()), int(ksp.getConvergedReason())
        relative, applied, eps = explicit(x, iterations, retain=True)
        # The terminal native action is part of the V7 30-second cost.  Do not
        # decide timeout status solely from the convergence callback.
        if bounded_policy:
            sample()
        terminal_seconds = seconds()
        if hard_seconds is not None and terminal_seconds >= hard_seconds:
            timeout_exceeded = True
            stop_reason = stop_reason or 'I4_HARD_TIME_EXCEEDED'
        if terminal_seconds >= soft_seconds:
            requested_safe_return = True
            stop_reason = stop_reason or 'I4_SAFE_RETURN_REQUESTED'
        # FGMRES Arnoldi rank saturation can be finite without solving the RHS.
        # This is distinct from NaN/Inf, PC failure, or unrelated solver failures.
        finite_reasons = (int(PETSc.KSP.ConvergedReason.DIVERGED_MAX_IT),
                          int(PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN))
        if reason < 0 and reason not in finite_reasons:
            raise RuntimeError(f'inner breakdown reason={reason}, true={relative}')
        finite_correction = False
        if bounded_policy and reason == int(PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN):
            try:
                finite_correction = (iterations > 0 and legal_direction_count > 0
                    and np.isfinite(x.norm()) and float(x.norm()) > 0.0)
            except (AttributeError, FloatingPointError, ValueError):
                finite_correction = False
        if (bounded_policy and reason == int(PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN)
                and not finite_correction):
            error = RuntimeError('V7 inner breakdown has no finite legal Krylov direction')
            error.bounded_i4_no_legal_direction = True
            raise error
        status = 'INNER_TARGET_REACHED' if relative <= target else ('INNER_APPROXIMATE_RETURN' if bounded_policy else 'INNER_INEXACT_AT_CAP')
        if bounded_policy and reason == int(PETSc.KSP.ConvergedReason.DIVERGED_BREAKDOWN):
            stop_reason = 'KRYLOV_BREAKDOWN_WITH_FINITE_RETURN'
        facts = dict(status=status, target=target, final_true_residual=relative,
            explicit_uses_separate_action=residual_action is not None,
            eps_norm=float(eps.norm()), rhs_norm=norm, iterations=iterations, reason=reason,
            restart=restart, max_it=max_it, zero_start=True, seconds=terminal_seconds,
            actual_elapsed_seconds=terminal_seconds, requested_safe_return=requested_safe_return,
            timeout_exceeded=timeout_exceeded, stop_reason=stop_reason or ('TARGET_REACHED' if relative <= target else 'MAX_IT'),
            legal_direction_count=legal_direction_count, history=history,
            A4_matvec=ac.matvec_count, B4_calls=context.apply_count,
            explicit_A4=explicit_count, attempted=dict(attempted), inner_basis_payload_bound=(2*restart+1)*rhs.getSize()*16,
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
    """One bounded factor; the explicitly supplied native action gates each solve."""
    action_identity = "native_A2"

    def __init__(self, matrix, action, slaves, *, sample, marker, save,
                 action_identity="native_A2", extra_local_bytes=0):
        from .fullspace_bounded_mumps import BoundedP1Factor
        self.bottom = BoundedP1Factor(matrix, label='physical_p2', resource_sample=sample,
            marker=marker, physical_p2_pilot=True, extra_local_bytes=extra_local_bytes)
        self.action_identity = action_identity
        self.bottom.audit['residual_action_identity'] = action_identity
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
                absolute = float(residual.norm())
                relative = absolute/norm if norm else absolute
                self.last_facts = dict(action_identity=self.action_identity, relative=relative, refinement=refinement,
                    residual_absolute=absolute, rhs_norm=norm,
                    counts={k:v-start.get(k,0) for k,v in self.counts.items()})
                if np.isfinite(relative) and relative <= 1e-10:
                    value=x; x=None; return value
            raise RuntimeError(self.action_identity+' residual exceeds 1e-10 after two refinements')
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


def build_recursive_physical_solver(cfg, comm, *, target, sample, marker, save, audit_every=32, observe_inner=None, stop_requested=lambda: False, bubble_enriched=False):
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
        p42, p64 = actions['transfers'][(4,2)], actions['transfers'][(6,4)]
        correction = None; extra = 0; bottom_action = actions['physical'][2]['physical_action']
        if bubble_enriched:
            from .physical_bubble_global import BubbleEnrichedSpace
            bubble = BubbleEnrichedSpace(levels, cfg, actions, sample=sample, marker=marker, save=save)
            bundle['bubble'] = bubble
            p42, correction, extra = bubble.transfer, bubble.insert_volume, bubble.retained_bytes
            bottom_action = bubble.composed_action
            bundle['numerical_storage']['bottom'] = 'bounded_bubble_enriched_S'
        matrix, facts = build_reference_matrix(levels, cfg, actions['physical'][2],
            actions['volume_quadrature_metadata'], marker=marker, sample=sample, degree=2, row_cap=8192,
            cell_volume_correction=correction, extra_local_bytes=extra)
        bundle['p2_matrix'], bundle['p2_matrix_facts'] = matrix, facts
        if bubble_enriched: bubble.qualify_matrix(matrix)
        bottom = PhysicalP2Inverse(matrix, bottom_action,
            owned_slave_indices(levels['spaces'][2], levels['floquets'][2]), sample=sample, marker=marker, save=save,
            action_identity='composed_WH_A4_W' if bubble_enriched else 'native_A2', extra_local_bytes=extra)
        bundle['p2_inverse'] = bottom
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
    for name in ('inexact_ledger', 'p2_inverse', 'p2_matrix', 'bubble'):
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
