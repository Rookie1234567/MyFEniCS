"""Task042 fixed bounded block PC and original-equation coarse adapter.

No global factor is created here. Only disjoint <=512-row patch LU factors,
the borrowed cell/port factors, and an already-owned exact A4 action are used.
"""

import time
import warnings

import numpy as np
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve

from .coarse_inverse_protocol import (
    CoarseState,
    FactorDeclaration,
    InversePlan,
    IterationReport,
    ResidualWitness,
)


class BoundedBlockPC:
    def __init__(self, rows, block_reader, *, cell_factor_bytes=0, width=512):
        if not 0 < width <= 6000 or rows <= width:
            raise ValueError("bounded patches must be smaller than the complete A4")
        if (rows * width * 16 + rows * 4 + cell_factor_bytes) > 512 * 2**20:
            raise ValueError("preconstruction worst-case PC factor budget exceeded")
        self.rows = rows
        self.factors = []
        self.seconds = 0.0
        for start in range(0, rows, width):
            stop = min(start + width, rows)
            block = np.array(
                block_reader(start, stop), dtype=np.complex128, order="F", copy=True
            )
            if (
                block.shape != (stop - start, stop - start)
                or not np.isfinite(block).all()
            ):
                raise ValueError("invalid patch block")
            with warnings.catch_warnings():
                warnings.simplefilter("error", LinAlgWarning)
                factor = lu_factor(block, overwrite_a=True, check_finite=False)
            self.factors.append((start, stop, factor))
        self.factor_bytes = sum(
            lu.nbytes + piv.nbytes for _, _, (lu, piv) in self.factors
        )
        if self.factor_bytes + cell_factor_bytes > 512 * 2**20:
            raise ValueError("actual factor payload exceeds budget")

    def apply_array(self, source):
        started = time.perf_counter()
        target = np.empty_like(source)
        for start, stop, factor in self.factors:
            target[start:stop] = lu_solve(
                factor, source[start:stop], check_finite=False
            )
        self.seconds += time.perf_counter() - started
        return target

    def apply(self, _pc, source, target):
        target.array[:] = self.apply_array(np.asarray(source.getArray(readonly=True)))

    @property
    def declarations(self):
        return tuple(
            FactorDeclaration("patch", stop - start, lu.nbytes + piv.nbytes)
            for start, stop, (lu, piv) in self.factors
        )


class OriginalEquationAudit:
    def __init__(self, action, native_apply):
        self.action = action
        self.native_apply = native_apply
        self.key = None
        self.cached_state = self.cached_rhs = None
        self.last = None

    def evaluate(self, state, rhs):
        key = (id(state), id(rhs))
        if state is not self.cached_state or rhs is not self.cached_rhs:
            a = self.action
            reduced = np.zeros(a.reduced_size, dtype=np.complex128)
            for original in a.condensed.trace_constraints.owned_active_original_dofs:
                reduced[
                    a.condensed.trace_constraints.original_to_active[int(original)]
                ] = state.fe[int(original)]
            reduced[a.condensed.active_rows :] = state.port
            self.last = a.evaluate_native_residual(
                reduced,
                rhs.fe,
                self.native_apply,
                port_rhs=rhs.port,
                rhs_is_mpc_dual=True,
            )
            # The submitted full field must equal independently recovered interiors.
            self.last["submitted_recovery_difference"] = (
                state.fe - self.last["storage_solution"]
            )
            self.key = key
            self.cached_state, self.cached_rhs = state, rhs
        return self.last

    def native(self, state, rhs):
        d = self.evaluate(state, rhs)
        return ResidualWitness(d["native_residual"], d["native_rhs_operation_scale"])

    def port(self, state, rhs):
        d = self.evaluate(state, rhs)
        return ResidualWitness(d["augmented_port_residual"], d["port_operation_scale"])

    def recovery(self, state, rhs):
        d = self.evaluate(state, rhs)
        # Two separately scaled conditions: local original equations and submitted storage.
        r1 = d["internal_residual"] / max(
            d["internal_operation_scale"], np.finfo(float).tiny
        )
        r2 = d["submitted_recovery_difference"] / max(
            np.linalg.norm(state.fe), np.finfo(float).tiny
        )
        return ResidualWitness(np.r_[r1, r2], 1.0)


class IterativeCoarseBackend:
    def __init__(self, matrix, action, pc, sha, cell_declarations):
        self.matrix = matrix
        self.action = action
        self.pc = pc
        self.plan = InversePlan(sha, tuple(cell_declarations) + pc.declarations)
        self.last_reduced = None
        self.history = []
        self.trajectory = []
        self.last_reason = None

    def solve(self, rhs):
        from petsc4py import PETSc

        b = self.matrix.createVecRight()
        x = b.duplicate()
        b.array[:] = self.action.reduce_rhs(
            rhs.fe, port_rhs=rhs.port, rhs_is_mpc_dual=True
        )
        x.set(0.0)
        ksp = PETSc.KSP().create(self.matrix.getComm())
        temporary = b.duplicate()
        try:
            ksp.setOperators(self.matrix)
            ksp.setType("fgmres")
            ksp.setGMRESRestart(32)
            ksp.setPCSide(PETSc.PC.Side.RIGHT)
            ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            ksp.setInitialGuessNonzero(False)
            ksp.setTolerances(rtol=1.0e-12, atol=0.0, max_it=256)
            ksp.getPC().setType("python")
            ksp.getPC().setPythonContext(self.pc)
            self.history = []
            self.trajectory = []

            def monitor(current, iteration, reported):
                self.history.append(
                    {"iteration": int(iteration), "reported": float(reported)}
                )
                if iteration in (0, 32, 128, 256):
                    if iteration == 0:
                        temporary.set(0.0)
                    else:
                        current.buildSolution(temporary)
                    v = self.matrix.createVecLeft()
                    self.matrix.mult(temporary, v)
                    residual = b.array - v.array
                    self.trajectory.append((int(iteration), residual.copy()))
                    v.destroy()

            ksp.setMonitor(monitor)
            ksp.solve(b, x)
            self.last_reduced = x.array.copy()
            self.last_reason = int(ksp.getConvergedReason())
            fe = self.action.recover_storage(
                self.last_reduced, full_rhs=rhs.fe, expand_trace=False
            )
            state = CoarseState(
                fe, self.last_reduced[self.action.condensed.active_rows :]
            )
            return state, IterationReport(int(ksp.getIterationNumber()))
        finally:
            temporary.destroy()
            ksp.destroy()
            x.destroy()
            b.destroy()


def native_numpy_apply(bundle):
    from petsc4py import PETSc

    from .fullspace_physical_intermediate import apply_owned

    def apply(values):
        source = PETSc.Vec().createSeq(len(values))
        source.array[:] = values
        output = None
        try:
            output = apply_owned(bundle["physical_action"], source)
            return output.array.copy()
        finally:
            if output is not None:
                output.destroy()
            source.destroy()

    return apply


def manufacture(action, native, field, alpha):
    d = action.apply_D_full(field)
    port = action.H_p @ alpha - d
    g = native(field) + action.apply_B_full(alpha - action.original_hp_solve(d))
    return g, port


def cell_declarations(action):
    result = []
    for factor in action.condensed.interior_lu_by_class.values():
        result.append(
            FactorDeclaration(
                "cell", factor[0].shape[0], factor[0].nbytes + factor[1].nbytes
            )
        )
    # Original DtN elimination is an explicitly bounded port bottom solve.
    result.append(
        FactorDeclaration(
            "bottom",
            action.condensed.appended_rows,
            action.H_p.nbytes + action.condensed.appended_rows * 4,
        )
    )
    return tuple(result)
