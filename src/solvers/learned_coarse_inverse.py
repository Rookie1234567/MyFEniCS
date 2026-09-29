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
    def __init__(
        self,
        matrix,
        action,
        pc,
        sha,
        cell_declarations,
        *,
        diagnostic_observer=None,
        observer_stride=1,
        state_capture=None,
        capture_stride=8,
        max_iterations=256,
    ):
        if max_iterations not in (64, 256) or observer_stride not in (1, 32):
            raise ValueError(
                "explicit bounded research iteration/monitoring profile required"
            )
        self.matrix = matrix
        self.action = action
        self.pc = pc
        self.plan = InversePlan(
            sha,
            tuple(cell_declarations) + pc.declarations,
            representation_bytes=getattr(pc, "representation_bytes", 0),
        )
        self.last_reduced = None
        self.history = []
        self.trajectory = []
        self.last_reason = None
        self.diagnostic_observer = diagnostic_observer
        self.observer_stride = observer_stride
        self.state_capture = state_capture
        self.capture_stride = capture_stride
        self.max_iterations = max_iterations
        self.costs = {}

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
        residual_vector = self.matrix.createVecLeft()
        try:
            ksp.setOperators(self.matrix)
            ksp.setType("fgmres")
            ksp.setGMRESRestart(32)
            ksp.setPCSide(PETSc.PC.Side.RIGHT)
            ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
            ksp.setInitialGuessNonzero(False)
            ksp.setTolerances(rtol=1.0e-12, atol=0.0, max_it=self.max_iterations)
            ksp.getPC().setType("python")
            ksp.getPC().setPythonContext(self.pc)
            self.history = []
            self.trajectory = []
            observed = set()
            self.costs = {
                "build_solution_seconds": 0.0,
                "explicit_monitor_S_seconds": 0.0,
                "explicit_monitor_S_calls": 0,
            }

            def observe(iteration, reported, values):
                started = time.perf_counter()
                temporary.array[:] = values
                self.matrix.mult(temporary, residual_vector)
                residual = b.array - residual_vector.array
                self.costs["explicit_monitor_S_seconds"] += (
                    time.perf_counter() - started
                )
                self.costs["explicit_monitor_S_calls"] += 1
                if self.observer_stride == 32 or iteration in (0, 32, 128, 256):
                    self.trajectory.append((int(iteration), residual.copy()))
                if self.diagnostic_observer is not None:
                    self.diagnostic_observer(
                        int(iteration),
                        float(reported),
                        temporary.array,
                        residual,
                        b.array,
                    )
                observed.add(int(iteration))

            def monitor(current, iteration, reported):
                self.history.append(
                    {"iteration": int(iteration), "reported": float(reported)}
                )
                audit_due = (
                    self.diagnostic_observer is not None
                    and iteration % self.observer_stride == 0
                ) or iteration in (0, 32, 128, 256)
                capture_due = (
                    self.state_capture is not None
                    and iteration > 0
                    and iteration % self.capture_stride == 0
                )
                if audit_due or capture_due:
                    started = time.perf_counter()
                    if iteration == 0:
                        temporary.set(0.0)
                    else:
                        current.buildSolution(temporary)
                    self.costs["build_solution_seconds"] += (
                        time.perf_counter() - started
                    )
                    if capture_due:
                        self.state_capture(int(iteration), temporary.array)
                    if audit_due:
                        observe(iteration, reported, temporary.array)

            ksp.setMonitor(monitor)
            started = time.perf_counter()
            ksp.solve(b, x)
            self.costs["ksp_seconds_inclusive"] = time.perf_counter() - started
            self.last_reduced = x.array.copy()
            self.last_reason = int(ksp.getConvergedReason())
            if (
                self.diagnostic_observer is not None
                and int(ksp.getIterationNumber()) not in observed
            ):
                observe(ksp.getIterationNumber(), ksp.getResidualNorm(), x.array)
            started = time.perf_counter()
            fe = self.action.recover_storage(
                self.last_reduced, full_rhs=rhs.fe, expand_trace=False
            )
            state = CoarseState(
                fe, self.last_reduced[self.action.condensed.active_rows :]
            )
            self.costs["final_recovery_seconds"] = time.perf_counter() - started
            return state, IterationReport(int(ksp.getIterationNumber()))
        except Exception:
            # Best available current state, without masking the original
            # failure. Nonfinite/operator failures may make this audit fail;
            # record that fact instead of manufacturing a valid witness.
            if self.diagnostic_observer is not None and self.history:
                try:
                    ksp.buildSolution(temporary)
                    observe(
                        ksp.getIterationNumber(), ksp.getResidualNorm(), temporary.array
                    )
                    self.costs["exception_full_audit_performed"] = True
                except Exception as audit_error:  # noqa: BLE001 -- preserve the original failure
                    self.costs["exception_audit_error_type"] = type(
                        audit_error
                    ).__name__
            raise
        finally:
            residual_vector.destroy()
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


def reference_solve(matrix, action, rhs, ksp):
    """Offline-only repeated factor application; never used by a candidate."""
    b = matrix.createVecRight()
    x = b.duplicate()
    residual = b.duplicate()
    correction = b.duplicate()
    try:
        b.array[:] = action.reduce_rhs(rhs.fe, port_rhs=rhs.port, rhs_is_mpc_dual=True)
        x.set(0.0)
        ksp.solve_repeated(b, x)
        refinements = 0
        for _ in range(3):
            matrix.mult(x, residual)
            residual.array[:] = b.array - residual.array
            if (
                np.linalg.norm(residual.array)
                / max(np.linalg.norm(b.array), np.finfo(float).tiny)
                <= 1.0e-13
            ):
                break
            ksp.solve_repeated(residual, correction)
            x.axpy(1.0, correction)
            refinements += 1
        return x.array.copy(), refinements
    finally:
        for v in (b, x, residual, correction):
            v.destroy()
