"""Diagnostic-only exact augmented physical middle inverse; no fine matrix."""
import time
import numpy as np
from petsc4py import PETSc

from .fullspace_v17_p3_oracle import _MumpsFactor, compile_physical_diagnostic_volume
from .fullspace_physical_intermediate import apply_owned


class ReferenceResourceBlocked(RuntimeError):
    pass


def reference_budget(sample, raw_info, future_bytes, *, marker=lambda *_: None):
    """Engineering forecast, never a measured factor or strict upper bound."""
    estimate_mb = int(raw_info['infog']['16'])
    if estimate_mb <= 0:
        raise ReferenceResourceBlocked('nonpositive/unavailable MUMPS estimate')
    estimate = (estimate_mb + 1)*1_000_000
    predicted = int(sample['rss_bytes']) + 2*estimate + int(future_bytes) + 1024**3
    facts = dict(post_symbolic_rss_bytes=int(sample['rss_bytes']),
        symbolic_factor_estimate_padded_bytes=estimate, factor_prediction_multiplier=2,
        future_workspace_bytes=int(future_bytes), engineering_buffer_bytes=1024**3,
        predicted_peak_bytes=predicted, launch_cap_bytes=int(sample['launch_cap_bytes']),
        classification='predicted_engineering_budget_not_upper_bound')
    marker('reference_budget_evaluated', dict(facts, numeric_called=False))
    if (not sample['all_status_readable'] or sample['swap_bytes'] != 0 or
            predicted >= sample['launch_cap_bytes']):
        raise ReferenceResourceBlocked(str(facts))
    return facts


def augment_physical_volume(volume, carrier):
    """Exactly preallocate [V B; -D H], using sparse carrier data as stored."""
    n = volume.getSize()[0]
    if volume.getComm().getSize() != 1 or carrier.global_rows != n:
        raise ValueError('reference augmentation requires MPI1 matching carrier')
    entries = carrier.entries
    sizes = np.empty(n + len(entries), dtype=PETSc.IntType)
    for row in range(n):
        columns, _ = volume.getRow(row)
        sizes[row] = len(columns)
    for j, item in enumerate(entries):
        sizes[item.coupling_rows] += 1
        sizes[n+j] = len(item.projection_rows)+1
    matrix = PETSc.Mat().createAIJ([len(sizes), len(sizes)], nnz=sizes, comm=volume.getComm())
    try:
        matrix.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, True)
        for row in range(n):
            columns, values = volume.getRow(row)
            if len(columns):
                matrix.setValues([row], columns, values)
        for j, item in enumerate(entries):
            if len(item.coupling_rows):
                matrix.setValues(item.coupling_rows, [n+j], item.coupling_values)
            if len(item.projection_rows):
                matrix.setValues([n+j], item.projection_rows, -item.projection_values)
            matrix.setValue(n+j, n+j, item.normalization_h)
        matrix.assemble()
        return matrix, dict(fe_rows=n, port_rows=len(entries), augmented_rows=len(sizes),
                            preallocated_nnz=int(sizes.sum()), allocated_nnz=int(matrix.getInfo()['nz_allocated']))
    except BaseException:
        matrix.destroy()
        raise


def build_reference_matrix(setup, cfg, native, quadrature, *, marker, sample):
    """Use MPC's exact sparsity constructor before numerical volume assembly."""
    import dolfinx_mpc
    space, mpc = setup['spaces'][4], setup['floquets'][4].mpc
    marker('reference_volume_compile_started', {})
    compiled = compile_physical_diagnostic_volume(setup, cfg, 4,
        volume_quadrature_metadata=quadrature)
    carrier = native['dtn_action'].carrier
    coefficients, offsets = mpc.coefficients()
    counts = np.diff(offsets)[np.asarray(mpc.slaves, dtype=np.int32)]
    marker('reference_metadata', dict(rows=int(space.dofmap.index_map.size_global),
        slaves=len(mpc.slaves), max_slave_links=int(max(counts, default=0)),
        port_count=len(carrier.entries),
        coupling_nnz=sum(len(e.coupling_rows)+len(e.projection_rows)+1 for e in carrier.entries)))
    sample()
    volume = dolfinx_mpc.cpp.mpc.create_matrix(compiled._cpp_object, mpc._cpp_object, mpc._cpp_object)
    try:
        marker('reference_volume_pattern', dict(allocated_nnz=int(volume.getInfo()['nz_allocated'])))
        sample()
        dolfinx_mpc.assemble_matrix(compiled, mpc, bcs=[], A=volume)
        marker('reference_volume_complete', dict(nnz=int(volume.getInfo()['nz_used'])))
        sample()
        matrix, facts = augment_physical_volume(volume, carrier)
        try:
            marker('reference_augmentation_complete', facts)
        except BaseException:
            matrix.destroy()
            raise
        return matrix, facts
    finally:
        volume.destroy()


class PhysicalP4Reference:
    """One symbolic/numeric factor, reused for RHS; original A4 gates every solve."""
    solver_identity = 'exact_augmented_A4_reference'

    def __init__(self, matrix, action, slave_indices, *, fine_rows, sample, marker,
                 factor_factory=_MumpsFactor):
        self.matrix, self.action = matrix, action
        self.slaves = np.asarray(slave_indices, dtype=np.int32)
        self.sample, self.marker = sample, marker
        self.factor = None
        self.audit = dict(diagnostic_only=True, solver_identity=self.solver_identity,
                          symbolic_calls=0, numeric_calls=0, solve_calls=0)
        try:
            marker('reference_symbolic_started', {})
            sample()
            self.factor = factor_factory(matrix)
            self.factor.symbolic(matrix)
            raw = self.factor.info((22,29))
            self.audit.update(symbolic_calls=1, symbolic_raw=raw)
            marker('reference_symbolic_complete', self.audit)
            # 65 V/Z plus 15 fine RHS/action/PC vectors; 16 p4/aug work vectors.
            # Includes recovery reserve conservatively, despite factor release first.
            future = 80*int(fine_rows)*16 + 16*matrix.getSize()[0]*16 + 256*1024**2
            resources = sample()
            marker('reference_symbolic_resource', dict(resource=resources, raw_info=raw,
                                                      numeric_called=False))
            self.audit['budget'] = reference_budget(resources, raw, future, marker=marker)
            marker('reference_numeric_preflight', self.audit['budget'])
            allowance = int((self.audit['budget']['launch_cap_bytes']-
                self.audit['budget']['post_symbolic_rss_bytes']-future-1024**3)//1_000_000)
            self.factor.set_memory_limit_mb(allowance)
            self.factor.numeric(matrix)
            self.audit.update(numeric_calls=1, numeric_raw=self.factor.info((22,29)))
            sample()
            marker('reference_numeric_complete', self.audit)
        except BaseException:
            self.destroy()
            raise

    def solve_intermediate(self, rhs):
        started = time.perf_counter()
        if not np.all(np.isfinite(rhs.array)) or np.any(rhs.array[self.slaves] != 0):
            raise ValueError('reference RHS must be finite legal slave-zero primal storage')
        self.sample()
        b, x = self.matrix.createVecRight(), self.matrix.createVecRight()
        solution = rhs.duplicate()
        try:
            b.set(0); b.array[:rhs.getLocalSize()] = rhs.array
            self.factor.solve_repeated(b, x)
            self.audit['solve_calls'] += 1
            solution.array[:] = x.array[:rhs.getLocalSize()]
            if not np.all(np.isfinite(solution.array)) or np.any(np.abs(solution.array[self.slaves]) > 1e-12):
                raise RuntimeError('reference solution has nonfinite/slave contamination')
            solution.array[self.slaves] = 0
            applied = apply_owned(self.action, solution)
            try:
                applied.axpy(-1, rhs)
                residual_norm, rhs_norm = applied.norm(), rhs.norm()
                relative = residual_norm/max(rhs_norm, np.finfo(float).tiny)
            finally:
                applied.destroy()
            facts = dict(status='REFERENCE_SOLVE_PASS', solver_identity=self.solver_identity,
                final_true_residual=float(relative) if np.isfinite(relative) else None,
                true_residual_norm=float(residual_norm) if np.isfinite(residual_norm) else None,
                rhs_norm=float(rhs_norm) if np.isfinite(rhs_norm) else None,
                elapsed_seconds=time.perf_counter()-started, iterations=0,
                factor_solve_calls=1, explicit_action_count=1, diagnostic_only=True,
                residual_limit=1e-10, residual_gate_passed=bool(np.isfinite(relative) and relative <= 1e-10))
            if not facts['residual_gate_passed']:
                facts['status'] = 'REFERENCE_RESIDUAL_REJECTED'
            self.marker('reference_residual_evaluated', facts)
            if not facts['residual_gate_passed']:
                raise RuntimeError(f'original A4 reference true residual {relative} exceeds 1e-10')
            self.marker('reference_solve_complete', facts)
            self.sample()
            return dict(facts, final_solution=solution)
        except BaseException:
            solution.destroy()
            raise
        finally:
            x.destroy(); b.destroy()

    def destroy(self):
        if self.factor is not None:
            self.factor.destroy(); self.factor = None
