"""Connect the fixed interface inverse directly to the existing BAL_H action."""

from copy import deepcopy
import time

import numpy as np

from .physical_balanced_coupling import PhysicalBalancedCoupling
from .physical_inexact_balance import InexactBalanceLedger


class InterfaceBalancedCoupling:
    """Borrow the operators and record both actual inexact p4 residuals.

    All operator callbacks and transfer methods return owned PETSc vectors.
    ``transfer`` is the qualified slave-zero algebraic P/P^H adapter.  No
    reference, initial guess, old I4 wrapper, or residual-minimization step
    enters this composition.
    """

    def __init__(self, fine_action, p4_action, transfer, fint, h6, *, save,
                 checkpoint=lambda: None, capture_vectors=False):
        self.p4_action, self.transfer, self.fint = p4_action, transfer, fint
        self.coarse_calls = []
        self.native_A4_count = 0
        self.ledger = InexactBalanceLedger(
            fine_action, transfer.apply_adjoint, save=save,
            checkpoint=checkpoint, every=32, mode='BAL_H',
            retain_call_vectors=capture_vectors)
        self.balanced = PhysicalBalancedCoupling(
            fine_action, self._coarse, h6, transfer.apply_adjoint,
            route='BAL_H', checkpoint=checkpoint, inexact_ledger=self.ledger,
            capture_vectors=capture_vectors)

    def _coarse(self, fine_rhs):
        g = self.transfer.apply_adjoint(fine_rhs)
        correction = applied = residual = None
        try:
            started = time.perf_counter()
            correction, interface = self.fint.apply_with_facts(g)
            self.native_A4_count += 1
            applied = self.p4_action(correction)
            residual = g.copy()
            residual.axpy(-1., applied)
            rhs_norm, residual_norm = float(g.norm()), float(residual.norm())
            facts = {
                'interface_facts': deepcopy(interface),
                'rhs_norm': rhs_norm,
                'native_A4_residual_norm': residual_norm,
                'native_A4_relative_residual': residual_norm / max(
                    rhs_norm, np.finfo(float).tiny),
                'fint_and_native_A4_seconds': time.perf_counter() - started,
                'native_A4_actions': 1,
            }
            self.ledger.record(g, applied, residual, facts)
            self.coarse_calls.append(facts)
            return self.transfer.apply_primal(correction)
        finally:
            for vector in (residual, applied, correction, g):
                if vector is not None:
                    vector.destroy()

    def apply(self, source):
        self.coarse_calls = []
        return self.balanced.apply(source)

    @property
    def apply_count(self):
        return self.balanced.apply_count

    @property
    def last_apply_facts(self):
        return self.balanced.last_apply_facts

    @property
    def last_apply_vectors(self):
        return self.balanced.last_apply_vectors

    def destroy(self):
        self.ledger.destroy()
        # These compact scalar facts remain useful after cleanup, especially
        # when a second coarse call or a resource boundary interrupts the PC.
        # They own no PETSc vectors or large arrays.
        self.balanced.last_apply_vectors.clear()
