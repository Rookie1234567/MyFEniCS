"""Bounded, explicit diagnostic refinement; ordinary p4 solves never use this."""
import numpy as np


class ReferenceAccuracyRejected(RuntimeError):
    def __init__(self, facts):
        self.facts = facts
        super().__init__('REFERENCE_ACCURACY_UNRESOLVED: ' + str(facts['final_true_residual']))


class ReferenceDependencySkipped(RuntimeError):
    def __init__(self, facts):
        self.facts=facts
        super().__init__('exact same p4 RHS already rejected')


class EvidenceBlocked(RuntimeError):
    pass


class ReferenceDefinitionMismatch(RuntimeError):
    pass


def residual_identity(g, y, a, native, augmented, volume, coupled_a, ch_rp, ch_dy):
    """The residual sign is g-A4y; port residual uses the original augmented a."""
    n = len(g)
    rf, rp = g-augmented[:n], -augmented[n:]
    r4 = g-native
    difference = r4-(rf-ch_rp)
    norm = lambda v: float(np.linalg.norm(v))
    gnorm = norm(g)
    scale = gnorm+norm(volume)+norm(coupled_a)+norm(ch_dy)
    return dict(g=g, y=y, a=a, A4y=native, r4=r4, rF=rf, rP=rp,
                CH_inverse_rP=ch_rp, identity_difference=difference,
                rhs_norm=gnorm, operation_scale=scale,
                final_true_residual=norm(r4)/max(gnorm, np.finfo(float).tiny),
                r4_norm=norm(r4), rF_norm=norm(rf), rP_norm=norm(rp),
                CH_inverse_rP_norm=norm(ch_rp),
                identity_relative_to_g=norm(difference)/max(gnorm, np.finfo(float).tiny),
                identity_relative_to_operations=norm(difference)/max(scale, np.finfo(float).tiny),
                residual_sign='g-A4y; legacy strict record uses the opposite vector sign')


class DiagnosticRefinementV4:
    """At most ten logical RHS and three external MatSolve calls per RHS."""
    name = 'diagnostic_refinement_v4'

    def __init__(self, save, carrier_action, control, identity):
        self.save_callback = save
        self.carrier_action = carrier_action
        self.control = np.array(control, copy=True)
        self.identity = identity
        self.logical_rhs = self.external_solves = 0
        self.label = 'unlabelled'
        self.records = []
        self.rejected_inputs = {}

    def save(self, name, facts):
        try:
            return self.save_callback(name, dict(facts, policy=self.name, identity=self.identity))
        except Exception as exc:
            raise EvidenceBlocked('required p4 packet could not be saved: '+name) from exc

    def before_middle(self, q, residual, g):
        self.save(self.label+'_before_middle', dict(q=q.array.copy(),
            post_pre_residual=residual.array.copy(), g=g.array.copy(),
            roles=dict(q='dual fine RHS', post_pre_residual='dual fine residual', g='dual p4 RHS')))

    def solve(self, reference, rhs):
        import hashlib
        from .fullspace_physical_intermediate import apply_owned
        g = rhs.array.copy()
        digest = hashlib.sha256(g.tobytes()).hexdigest()
        if digest in self.rejected_inputs:
            facts=dict(g=g, g_sha256=digest, dependency=self.rejected_inputs[digest],
                       status='skipped', reason='exact identical rejected RHS; unchanged factor and action')
            self.save(self.label+'_same_rejected_input',facts)
            raise ReferenceDependencySkipped(dict(facts,g=None))
        self.logical_rhs += 1
        if self.logical_rhs > 10:
            raise RuntimeError('diagnostic logical p4 RHS budget exceeded')
        logical = self.logical_rhs
        prefix = self.label+f'_p4_{logical:02d}'
        self.save(prefix+'_input', dict(g=g, g_sha256=digest, logical_rhs=logical, roles=dict(g='dual p4 RHS')))
        if not np.isfinite(g).all() or np.any(g[reference.slaves] != 0):
            raise ValueError('p4 diagnostic RHS must be finite and slave-zero')
        reference.sample()
        n = len(g)
        b, state = reference.matrix.createVecRight(), reference.matrix.createVecRight()
        scratch, applied = reference.matrix.createVecRight(), reference.matrix.createVecRight()
        solution, zero, coupled = rhs.duplicate(), rhs.duplicate(), rhs.duplicate()
        delta = reference.matrix.createVecRight()
        b.set(0); b.array[:n] = g
        state.set(0); zero.set(0)
        h = np.array([e.normalization_h for e in self.carrier_action.carrier.entries])
        original_norm = max(float(np.linalg.norm(g)), np.finfo(float).tiny)

        def augmented(v):
            scratch.array[:] = v
            reference.matrix.mult(scratch, applied)
            return applied.array.copy()

        def coupling(v):
            self.carrier_action.compose_physical_rhs(zero, v, coupled)
            return coupled.array.copy()

        def native(v):
            solution.array[:] = v
            output = apply_owned(reference.action, solution)
            try:
                return output.array.copy()
            finally:
                output.destroy()

        def action_control(v, label):
            av = native(v)
            ports = self.carrier_action.recover_auxiliary(solution)
            assembled = augmented(np.r_[v, ports])
            relative = float(np.linalg.norm(assembled[:n]-av)/max(np.linalg.norm(av), np.finfo(float).tiny))
            self.save(prefix+'_'+label, dict(y=v, reconstructed_port=ports,
                native_action=av, assembled_action=assembled[:n], port_block=assembled[n:],
                relative=relative, limit=1e-10,
                roles=dict(y='primal p4 control', reconstructed_port='separate diagnostic reconstruction')))
            if not np.isfinite(relative) or relative > 1e-10:
                raise ReferenceDefinitionMismatch('native/assembled p4 action mismatch: '+str(relative))

        last = None
        try:
            settings = reference.factor.refinement_settings()
            for iteration in range(3):
                if np.linalg.norm(b.array) != 0:
                    if self.external_solves >= 30:
                        raise RuntimeError('external MatSolve budget exceeded')
                    self.external_solves += 1
                    reference.factor.solve_repeated(b, delta)
                    reference.audit['solve_calls'] += 1
                    state.axpy(1., delta)
                    delta_norm = float(np.linalg.norm(delta.array[:n]))
                else:
                    delta.set(0); delta_norm = 0.
                original_state = state.array.copy()
                y = original_state[:n].copy()
                a = original_state[n:].copy()
                # Save the untouched factor state even when validation must reject it.
                self.save(prefix+f'_state_{iteration}', dict(augmented_rhs=b.array.copy(),
                    original_augmented_rhs=np.r_[g,np.zeros_like(a)],
                    augmented_state=original_state, delta=delta.array.copy(), iteration=iteration,
                    roles=dict(augmented_rhs='dual correction RHS; original g retained separately',
                               augmented_state='cumulative primal y and original cumulative port a',
                               delta='primal augmented correction')))
                if not np.isfinite(original_state).all() or np.any(np.abs(y[reference.slaves]) > 1e-12):
                    raise ValueError('p4 diagnostic solution nonfinite or slave contaminated')
                y[reference.slaves] = 0
                evaluated_state = np.r_[y, a]
                av = native(y)
                combined = augmented(evaluated_state)
                volume_state = augmented(np.r_[y, np.zeros_like(a)])
                rp = -combined[n:]
                ch_rp = coupling(rp/h)
                ch_dy = coupling(-volume_state[n:]/h)
                coupled_a = coupling(a)
                raw = dict(A4y=av, augmented_action=combined, volume_action=volume_state,
                           CH_inverse_rP=ch_rp, CH_inverse_Dy=ch_dy, Ca=coupled_a)
                self.save(prefix+f'_actions_{iteration}', raw)
                if not all(np.isfinite(v).all() for v in raw.values()):
                    raise ValueError('nonfinite p4 diagnostic action')
                facts = residual_identity(g, y, a, av, combined, volume_state[:n], coupled_a, ch_rp, ch_dy)
                facts.update(iteration=iteration, logical_rhs=logical,
                    external_solves=self.external_solves, augmented_state=original_state,
                    evaluated_state=evaluated_state,
                    augmented_residual=np.r_[g, np.zeros_like(a)]-combined,
                    delta=delta.array.copy(), delta_y_relative=delta_norm/max(np.linalg.norm(y),np.finfo(float).tiny),
                    original_rhs_norm=original_norm, mumps_internal_refinement=settings,
                    residual_change=None if last is None else facts['final_true_residual']-last,
                    roles=dict(g='dual p4 RHS', y='primal p4 field', a='original cumulative port state',
                               r4='dual g-A4y', rF='dual FE block residual', rP='dual port block residual'))
                self.save(prefix+f'_residual_{iteration}', facts)
                if not all(np.isfinite(facts[k]) for k in ('final_true_residual','identity_relative_to_g','identity_relative_to_operations')):
                    raise ValueError('nonfinite p4 diagnostic residual')
                # Only the reconstructed first y and one predeclared legal control.
                if logical == 1 and iteration == 0:
                    action_control(y, 'reconstructed_y_action')
                    action_control(self.control, 'existing_control_action')
                if facts['identity_relative_to_operations'] > 1e-10:
                    raise ReferenceDefinitionMismatch('augmented/native residual identity mismatch')
                passed = facts['final_true_residual'] <= 1e-10
                status = ('REFERENCE_PASS_INITIAL' if iteration == 0 else 'REFERENCE_PASS_AFTER_REFINEMENT') if passed else 'REFERENCE_ACCURACY_UNRESOLVED'
                terminal = dict(status=status, final_true_residual=facts['final_true_residual'],
                    logical_rhs=logical, refinement_steps=iteration, residual_gate_passed=passed,
                    residual_limit=1e-10, original_rhs_norm=original_norm,
                    external_solves=self.external_solves, policy=self.name,
                    action_identity='REFINED_DIAGNOSTIC_ACTION' if iteration else 'INITIAL_DIAGNOSTIC_ACTION',
                    reconstructed_failure_status=('ORIGINAL_REJECTION_NOT_REPRODUCED' if passed else 'ORIGINAL_REJECTION_REPRODUCED') if logical == 1 and iteration == 0 else None)
                self.save(prefix+f'_decision_{iteration}', terminal)
                reference.marker('reference_diagnostic_evaluated', terminal)
                if passed:
                    self.records.append(terminal)
                    solution.array[:] = y
                    result = solution.copy()
                    return dict(terminal, final_solution=result)
                if iteration == 2:
                    self.records.append(terminal)
                    self.rejected_inputs[digest]=dict(terminal,label=self.label,g_sha256=digest)
                    raise ReferenceAccuracyRejected(terminal)
                last = facts['final_true_residual']
                b.set(0); b.array[:n] = facts['r4']
                reference.sample()
        finally:
            import sys
            primary = sys.exc_info()[1]
            errors = []
            for vector in (delta, coupled, zero, solution, applied, scratch, state, b):
                try:
                    vector.destroy()
                except Exception as exc:
                    errors.append(dict(type=type(exc).__name__,message=str(exc)))
            if errors:
                self.save(prefix+'_cleanup_errors',dict(errors=errors,primary_error=None if primary is None else str(primary)))
                raise RuntimeError('p4 diagnostic vector cleanup failed') from primary
