"""Owner-local distributed trace-harmonic construction.

The module keeps the D1 definition but replaces its dense fixture algebra with
PETSc MatShell actions.  Each slab owns an independent
``K_i q = lambda M_Gamma,i q`` problem.  The selected slab-local candidates
are ordered by ``(lambda, slab_id, local_index)`` and only their prefixes are
embedded into the owner-sharded full space.  No physical forcing vector is
accepted by this API; the basis depends only on the resolved mesh, materials,
MPC and the two fixed D1 forms.
"""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from types import MappingProxyType
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc
from slepc4py import SLEPc

from .fullspace_trace_harmonic import TraceHarmonicDefinition
from .hcurl_canonical_vector_dolfinx import (
    extract_canonical_full_fe_packets,
    reconstruct_canonical_full_fe_function,
)


D2_PROFILE = "adaptive_trace_harmonic_distributed_v1"
D2_MAX_EIGENPAIRS = 64
D2_KSP_RTOL = 1.0e-12
D2_KSP_MAX_IT = 500
D2_EPS_TOL = 1.0e-10
D2_EPS_MAX_IT = 500
D2_SHARED_TRACE_WEIGHT = 0.5
D2_RANK_PREFIXES = (16, 32, 48, 64)
D2_PHASE_ZERO = 64.0 * np.finfo(np.float64).eps


def _python_mat(
    context: Any,
    local_rows: int,
    global_rows: int,
    local_columns: int,
    global_columns: int,
    comm: Any,
) -> PETSc.Mat:
    matrix = PETSc.Mat().createPython(
        ((int(local_rows), int(global_rows)),
         (int(local_columns), int(global_columns))),
        context=context,
        comm=comm,
    )
    matrix.setUp()
    return matrix


def _owned_rows(function_space: Any) -> tuple[int, int, int]:
    index_map = function_space.dofmap.index_map
    owned = int(index_map.size_local)
    ghosts = int(index_map.num_ghosts)
    return owned, ghosts, owned + ghosts


def _ordered_slab_definitions(
    definitions: tuple[TraceHarmonicDefinition, ...],
) -> tuple[TraceHarmonicDefinition, ...]:
    ordered = tuple(sorted(definitions, key=lambda item: int(item.slab_id)))
    if tuple(int(item.slab_id) for item in ordered) != (0, 1):
        raise ValueError("D2 basis requires definitions for slab 0 and 1")
    return ordered


def _owned_row_slab_masks(
    definition: TraceHarmonicDefinition,
    function_space: Any,
) -> tuple[np.ndarray, np.ndarray]:
    """Route cell support bits to the PETSc owner of each full-space row.

    Only global row ids and two slab bits cross MPI.  The numeric vectors remain
    owner-local; the small ownership-range exchange is metadata, not a numeric
    allgather.
    """

    topology = definition.topology
    mpc = definition.mpc
    comm = topology.mesh.comm
    index_map = function_space.dofmap.index_map
    owned = int(index_map.size_local)
    start = int(comm.scan(owned, op=MPI.SUM) - owned)
    ranges = comm.allgather((start, start + owned))
    slab_ids = np.asarray(topology.owned_slab_ids, dtype=np.int8)
    send = [[] for _rank in range(comm.size)]
    for cell, slab_id in enumerate(slab_ids):
        local_rows = np.asarray(
            function_space.dofmap.cell_dofs(int(cell)), dtype=np.int32
        )
        global_rows = np.asarray(
            index_map.local_to_global(local_rows), dtype=PETSc.IntType
        )
        for global_row in global_rows:
            row = int(global_row)
            owner = next(
                rank
                for rank, (lower, upper) in enumerate(ranges)
                if lower <= row < upper
            )
            send[owner].append((row, int(slab_id)))
    received = comm.alltoall(send)
    rows_by_slab = [set(), set()]
    for records in received:
        for global_row, slab_id in records:
            local_row = int(global_row) - start
            if 0 <= local_row < owned:
                rows_by_slab[int(slab_id)].add(local_row)
    slave_rows = {int(row) for row in np.asarray(mpc.slaves, dtype=np.int32)}
    return tuple(
        np.asarray(sorted(rows - slave_rows), dtype=np.int32)
        for rows in rows_by_slab
    )


def _seed_value(key: str) -> complex:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    real = int.from_bytes(digest[:8], "big") / float(1 << 64)
    imag = int.from_bytes(digest[8:16], "big") / float(1 << 64)
    return complex(0.5 + real, -0.25 + imag)


def _relative_norm(value: PETSc.Vec, reference: PETSc.Vec) -> float:
    return float(value.norm() / max(reference.norm(), 1.0e-300))


def _stable_eigen_order(
    values: tuple[float, ...],
) -> tuple[tuple[tuple[float, int], ...], tuple[int, ...]]:
    """Return sorted eigenvalues and their stable original positions."""

    permutation = tuple(
        sorted(
            range(len(values)),
            key=lambda position: (float(values[position]), int(position)),
        )
    )
    ordered = tuple(
        (float(values[position]), int(ordinal))
        for ordinal, position in enumerate(permutation)
    )
    return ordered, permutation


class _TraceLift:
    """MatShell that injects compact owner-local trace rows into full space."""

    def __init__(
        self,
        full_template: PETSc.Vec,
        trace_rows: np.ndarray,
        trace_global_size: int,
    ) -> None:
        self._trace_rows = np.asarray(trace_rows, dtype=np.int32).copy()
        self._full_local, self._full_global = map(int, full_template.getSizes())
        self._trace_local = int(self._trace_rows.size)
        self._trace_global = int(trace_global_size)
        self.matrix = _python_mat(
            self,
            self._full_local,
            self._full_global,
            self._trace_local,
            self._trace_global,
            full_template.getComm(),
        )

    def mult(
        self, _matrix: PETSc.Mat, input_vector: PETSc.Vec, output: PETSc.Vec
    ) -> None:
        output_values = output.getArray()
        input_values = input_vector.getArray(readonly=True)
        output_values[:] = 0.0
        output_values[self._trace_rows] = input_values

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        matrix = self.matrix
        self.matrix = None
        if matrix is not None and _matrix is None:
            matrix.destroy()


class _InteriorRestricted:
    """B_II MatShell with identity complement and zero complement RHS use."""

    def __init__(
        self,
        action_matrix: PETSc.Mat,
        full_template: PETSc.Vec,
        interior_rows: np.ndarray,
    ) -> None:
        self._action_matrix = action_matrix
        self._interior_rows = np.asarray(interior_rows, dtype=np.int32).copy()
        self._input = full_template.duplicate()
        self._action_output = full_template.duplicate()
        local, global_size = map(int, full_template.getSizes())
        self.matrix = _python_mat(
            self,
            local,
            global_size,
            local,
            global_size,
            full_template.getComm(),
        )

    def mult(
        self, _matrix: PETSc.Mat, input_vector: PETSc.Vec, output: PETSc.Vec
    ) -> None:
        input_values = input_vector.getArray(readonly=True)
        with self._input.localForm() as local:
            local.set(0.0)
            local.array_w[self._interior_rows] = input_values[
                self._interior_rows
            ]
        self._input.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        self._action_matrix.mult(self._input, self._action_output)
        output_values = output.getArray()
        output_values[:] = input_values
        output_values[self._interior_rows] = self._action_output.getArray(
            readonly=True
        )[self._interior_rows]

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        matrix = self.matrix
        self.matrix = None
        if matrix is not None and _matrix is None:
            matrix.destroy()
        self._input.destroy()
        self._action_output.destroy()


class _TraceStiffness:
    def __init__(self, slab: "DistributedTraceHarmonicSlab") -> None:
        self._slab = slab
        self.matrix = _python_mat(
            self,
            slab._trace_local,
            slab._trace_global,
            slab._trace_local,
            slab._trace_global,
            slab.comm,
        )

    def mult(
        self, _matrix: PETSc.Mat, input_vector: PETSc.Vec, output: PETSc.Vec
    ) -> None:
        extension = self._slab._extend(input_vector)
        try:
            action_result = self._slab._auxiliary.apply(extension)
            output_values = output.getArray()
            output_values[:] = action_result.getArray(readonly=True)[
                self._slab.trace_rows
            ]
        finally:
            extension.destroy()

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        matrix = self.matrix
        self.matrix = None
        if matrix is not None and _matrix is None:
            matrix.destroy()


class _TraceMass:
    def __init__(self, slab: "DistributedTraceHarmonicSlab") -> None:
        self._slab = slab
        self._full_input = slab._auxiliary.matrix.createVecRight()
        self.matrix = _python_mat(
            self,
            slab._trace_local,
            slab._trace_global,
            slab._trace_local,
            slab._trace_global,
            slab.comm,
        )

    def mult(
        self, _matrix: PETSc.Mat, input_vector: PETSc.Vec, output: PETSc.Vec
    ) -> None:
        self._slab._lift.matrix.mult(input_vector, self._full_input)
        action_result = self._slab._interface_mass.apply(self._full_input)
        output.getArray()[:] = action_result.getArray(readonly=True)[
            self._slab.trace_rows
        ]

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        matrix = self.matrix
        self.matrix = None
        if matrix is not None and _matrix is None:
            matrix.destroy()
        self._full_input.destroy()


def _two_pass_mgs(
    columns: list[np.ndarray], comm: Any
) -> tuple[np.ndarray, ...]:
    orthogonal: list[np.ndarray] = []
    for column in columns:
        value = np.asarray(column, dtype=np.complex128).copy()
        for _pass in range(2):
            for previous in orthogonal:
                coefficient = comm.allreduce(
                    np.vdot(previous, value), op=MPI.SUM
                )
                value -= coefficient * previous
        norm_squared = float(
            comm.allreduce(np.vdot(value, value).real, op=MPI.SUM)
        )
        if not np.isfinite(norm_squared) or norm_squared <= 1.0e-28:
            raise RuntimeError("distributed trace columns are linearly dependent")
        value /= np.sqrt(norm_squared)
        orthogonal.append(value)
    return tuple(orthogonal)


def _phase_key_and_value(
    function_space: Any,
    floquet_data: Any,
    vector: PETSc.Vec,
) -> tuple[str, complex] | None:
    packets, _audit = extract_canonical_full_fe_packets(
        function_space, vector, floquet_data
    )
    candidates = []
    for key, packet_value in packets:
        value = complex(packet_value)
        if abs(value) <= D2_PHASE_ZERO:
            continue
        key = json.dumps(
            key, sort_keys=True, separators=(",", ":"), default=repr
        )
        candidates.append((key, value))
    local = min(candidates, default=None, key=lambda item: item[0])
    petsc_comm = vector.getComm()
    comm = (
        petsc_comm
        if hasattr(petsc_comm, "gather")
        else petsc_comm.tompi4py()
    )
    gathered = comm.gather(local, root=0)
    chosen = None
    if comm.rank == 0:
        available = [item for item in gathered if item is not None]
        chosen = min(available, default=None, key=lambda item: item[0])
    return comm.bcast(chosen, root=0)


class DistributedTraceHarmonicSlab:
    """One independent owner-local slab generalized eigenproblem."""

    def __init__(
        self,
        definition: TraceHarmonicDefinition,
        *,
        shared_trace_weight: float = D2_SHARED_TRACE_WEIGHT,
        slab_row_support: np.ndarray | None = None,
    ) -> None:
        if int(definition.slab_id) not in (0, 1):
            raise ValueError("distributed D2 core requires slab id 0 or 1")
        if float(shared_trace_weight) != D2_SHARED_TRACE_WEIGHT:
            raise ValueError("shared trace weight is fixed at 0.5")
        self.topology = definition.topology
        self.comm = self.topology.mesh.comm
        self.slab_id = int(definition.slab_id)
        self._function_space = definition.mpc.function_space
        self._owned_rows, self._ghost_rows, _storage = _owned_rows(
            self._function_space
        )
        if slab_row_support is None:
            slab_row_support = _owned_row_slab_masks(
                definition, self._function_space
            )[self.slab_id]
        support = np.asarray(slab_row_support, dtype=np.int32)
        self.trace_rows = np.asarray(
            self.topology.owned_trace_local_rows, dtype=np.int32
        )
        if self.trace_rows.size == 0:
            raise RuntimeError("slab has no owned active trace rows")
        self.interior_rows = np.setdiff1d(support, self.trace_rows)
        self.interior_rows = np.asarray(self.interior_rows, dtype=np.int32)
        self._trace_local = int(self.trace_rows.size)
        prefix = int(
            self.comm.scan(self._trace_local, op=MPI.SUM)
            - self._trace_local
        )
        self._trace_offset = prefix
        self._trace_global = int(
            self.comm.allreduce(self._trace_local, op=MPI.SUM)
        )
        self._auxiliary, self._interface_mass = definition.build_actions()
        self._full_template = self._auxiliary.matrix.createVecRight()
        self._lift = _TraceLift(
            self._full_template, self.trace_rows, self._trace_global
        )
        self._bii = _InteriorRestricted(
            self._auxiliary.matrix,
            self._full_template,
            self.interior_rows,
        )
        self._ksp = PETSc.KSP().create(self.comm)
        self._ksp.setType(PETSc.KSP.Type.CG)
        self._ksp.getPC().setType(PETSc.PC.Type.NONE)
        self._ksp.setTolerances(
            rtol=D2_KSP_RTOL,
            atol=0.0,
            max_it=D2_KSP_MAX_IT,
        )
        self._ksp.setOperators(self._bii.matrix)
        self._ksp.setInitialGuessNonzero(False)
        self._stiffness = _TraceStiffness(self)
        self._mass = _TraceMass(self)
        self._destroyed = False
        self._eigen_audit: dict[str, Any] = {}
        self._max_extension_residual = 0.0

    @property
    def trace_matrix(self) -> PETSc.Mat:
        return self._lift.matrix

    @property
    def stiffness_matrix(self) -> PETSc.Mat:
        return self._stiffness.matrix

    @property
    def mass_matrix(self) -> PETSc.Mat:
        return self._mass.matrix

    def create_trace_vector(self) -> PETSc.Vec:
        return self._mass.matrix.createVecRight()

    def create_full_vector(self) -> PETSc.Vec:
        return self._auxiliary.matrix.createVecRight()

    def _extend(self, trace_vector: PETSc.Vec) -> PETSc.Vec:
        lifted = self._auxiliary.matrix.createVecRight()
        solution = self._auxiliary.matrix.createVecRight()
        rhs = self._auxiliary.matrix.createVecRight()
        residual = self._auxiliary.matrix.createVecRight()
        try:
            self._lift.matrix.mult(trace_vector, lifted)
            action_result = self._auxiliary.apply(lifted)
            with rhs.localForm() as local:
                local.set(0.0)
                local.array_w[self.interior_rows] = -action_result.getArray(
                    readonly=True
                )[self.interior_rows]
            rhs.ghostUpdate(
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )
            solution.set(0.0)
            self._ksp.solve(rhs, solution)
            reason = int(self._ksp.getConvergedReason())
            if reason <= 0:
                raise RuntimeError(
                    f"slab {self.slab_id} interior CG did not converge: {reason}"
                )
            self._bii.matrix.mult(solution, residual)
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            relative = _relative_norm(residual, rhs)
            if not np.isfinite(relative) or relative > 1.0e-10:
                raise RuntimeError(
                    f"slab {self.slab_id} interior residual {relative} exceeds 1e-10"
                )
            self._max_extension_residual = max(
                self._max_extension_residual, float(relative)
            )
            lifted.axpy(PETSc.ScalarType(1.0), solution)
            if not np.array_equal(
                lifted.getArray(readonly=True)[self.trace_rows],
                trace_vector.getArray(readonly=True),
            ):
                raise RuntimeError("harmonic extension changed fixed trace rows")
            return lifted.copy()
        finally:
            lifted.destroy()
            solution.destroy()
            rhs.destroy()
            residual.destroy()

    def _seed_vector(self, salt: int) -> PETSc.Vec:
        """Make one deterministic trace seed through the public canonical map."""

        zero = self.create_full_vector()
        field = None
        vector = None
        try:
            zero.set(0.0)
            zero.assemble()
            packets, _audit = extract_canonical_full_fe_packets(
                self._function_space, zero, self.topology.floquet_data
            )
            seeded_packets = tuple(
                (
                    key,
                    _seed_value(
                        json.dumps(
                            key,
                            sort_keys=True,
                            separators=(",", ":"),
                            default=repr,
                        )
                        + f":{int(salt)}"
                    ),
                )
                for key, _value in packets
            )
            field = reconstruct_canonical_full_fe_function(
                self._function_space,
                seeded_packets,
                self.topology.floquet_data,
            )
            vector = self._mass.matrix.createVecRight()
            vector.getArray()[:] = field.x.petsc_vec.getArray(
                readonly=True
            )[self.trace_rows]
            vector.assemble()
            return vector
        except Exception:
            if vector is not None:
                vector.destroy()
            raise
        finally:
            if field is not None:
                del field
            zero.destroy()

    def _phase_fix(self, vector: PETSc.Vec) -> tuple[str, complex] | None:
        extension = self._extend(vector)
        try:
            selected = _phase_key_and_value(
                self._function_space, self.topology.floquet_data, extension
            )
        finally:
            extension.destroy()
        if selected is None:
            raise RuntimeError("harmonic eigenvector has no nonzero canonical packet")
        _key, value = selected
        phase = np.exp(-1j * np.angle(value))
        vector.scale(PETSc.ScalarType(phase))
        return selected

    def solve_eigenpairs(
        self,
        requested_eigenpairs: int = D2_MAX_EIGENPAIRS,
    ) -> tuple[
        tuple[tuple[float, int], ...],
        tuple[PETSc.Vec, ...],
    ]:
        requested = int(requested_eigenpairs)
        if requested < 1 or requested > D2_MAX_EIGENPAIRS:
            raise ValueError("requested eigenpairs must be in 1..64")
        nev = min(requested, self._trace_global)
        ncv = min(self._trace_global, max(2 * nev + 20, nev + 1))
        eps = SLEPc.EPS().create(self.comm)
        initial_space: list[PETSc.Vec] = []
        vectors: list[PETSc.Vec] = []
        eigen_residuals: list[float] = []
        success = False
        try:
            for salt in range(nev):
                initial_space.append(self._seed_vector(salt))
            eps.setOperators(self._stiffness.matrix, self._mass.matrix)
            eps.setProblemType(SLEPc.EPS.ProblemType.GHEP)
            eps.setType(SLEPc.EPS.Type.KRYLOVSCHUR)
            eps.setWhichEigenpairs(SLEPc.EPS.Which.SMALLEST_REAL)
            spectral_transform = eps.getST()
            spectral_transform.setType(SLEPc.ST.Type.SHIFT)
            spectral_transform.setShift(0.0)
            spectral_ksp = spectral_transform.getKSP()
            spectral_ksp.setType(PETSc.KSP.Type.CG)
            spectral_ksp.getPC().setType(PETSc.PC.Type.NONE)
            spectral_ksp.setTolerances(
                rtol=D2_KSP_RTOL,
                atol=0.0,
                max_it=D2_KSP_MAX_IT,
            )
            eps.setDimensions(nev=nev, ncv=ncv)
            eps.setTolerances(tol=D2_EPS_TOL, max_it=D2_EPS_MAX_IT)
            eps.setInitialSpace(initial_space)
            eps.solve()
            reason = int(eps.getConvergedReason())
            converged = int(eps.getConverged())
            if reason <= 0 or converged < nev:
                raise RuntimeError(
                    f"slab {self.slab_id} generalized eigenproblem did not "
                    f"converge: reason={reason}, converged={converged}, nev={nev}"
                )
            values: list[tuple[float, int]] = []
            for index in range(nev):
                eigenvalue = complex(eps.getEigenvalue(index))
                if not np.isfinite(eigenvalue.real) or not np.isfinite(
                    eigenvalue.imag
                ):
                    raise RuntimeError("generalized eigenvalue is not finite")
                vector = self._mass.matrix.createVecRight()
                try:
                    eps.getEigenvector(index, vector)
                    mass_vector = self._mass.matrix.createVecLeft()
                    try:
                        self._mass.matrix.mult(vector, mass_vector)
                        mass_norm = complex(vector.dot(mass_vector))
                    finally:
                        mass_vector.destroy()
                    if not np.isfinite(mass_norm.real) or mass_norm.real <= 0.0:
                        raise RuntimeError(
                            "generalized eigenvector mass norm is invalid"
                        )
                    vector.scale(
                        PETSc.ScalarType(1.0 / np.sqrt(mass_norm.real))
                    )
                    self._phase_fix(vector)
                    stiffness_vector = self._stiffness.matrix.createVecLeft()
                    mass_vector = self._mass.matrix.createVecLeft()
                    eigen_residual = None
                    try:
                        self._stiffness.matrix.mult(vector, stiffness_vector)
                        self._mass.matrix.mult(vector, mass_vector)
                        eigen_residual = stiffness_vector.copy()
                        eigen_residual.axpy(
                            PETSc.ScalarType(-eigenvalue.real), mass_vector
                        )
                        denominator = max(
                            stiffness_vector.norm(),
                            abs(eigenvalue.real) * mass_vector.norm(),
                            1.0e-300,
                        )
                        relative = float(eigen_residual.norm() / denominator)
                    finally:
                        if eigen_residual is not None:
                            eigen_residual.destroy()
                        stiffness_vector.destroy()
                        mass_vector.destroy()
                    if not np.isfinite(relative) or relative > 1.0e-10:
                        raise RuntimeError(
                            f"slab {self.slab_id} eigen residual {relative} "
                            "exceeds 1e-10"
                        )
                    eigen_residuals.append(relative)
                    values.append((float(eigenvalue.real), int(index)))
                    vectors.append(vector)
                    vector = None
                finally:
                    if vector is not None:
                        vector.destroy()
            ordered_values, permutation = _stable_eigen_order(
                tuple(item[0] for item in values)
            )
            ordered_vectors = tuple(vectors[index] for index in permutation)
            self._eigen_audit = {
                "eigenproblem": "distributed_owner_local_GHEP_KRYLOVSCHUR",
                "eigensolver": "krylovschur_matrix_free_mass_inverse_cg_none",
                "problem_type": "GHEP",
                "which": "smallest_real",
                "nev": nev,
                "ncv": ncv,
                "tol": D2_EPS_TOL,
                "max_it": D2_EPS_MAX_IT,
                "spectral_transform": "shift_zero",
                "spectral_ksp": "cg",
                "spectral_pc": "none",
                "spectral_ksp_rtol": D2_KSP_RTOL,
                "spectral_ksp_max_it": D2_KSP_MAX_IT,
                "shift_invert": False,
                "initial_vectors": "sha256(canonical_full_fe_packet)+salt_0_to_nev_minus_1",
                "phase_anchor": "minimum_nonzero_harmonic_full_fe_packet",
                "degenerate_phase_policy": "expose_subspace_no_anchor",
                "eigen_residual_max": float(
                    max(eigen_residuals, default=0.0)
                ),
                "harmonic_extension_residual_max": float(
                    self._max_extension_residual
                ),
            }
            success = True
            return ordered_values, ordered_vectors
        finally:
            for seed in initial_space:
                seed.destroy()
            if not success:
                for vector in vectors:
                    vector.destroy()
            eps.destroy()

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._stiffness.destroy()
        self._mass.destroy()
        self._ksp.destroy()
        self._bii.destroy()
        self._lift.destroy()
        self._full_template.destroy()
        self._auxiliary.destroy()
        self._interface_mass.destroy()


class DistributedTraceHarmonicBasis:
    """Stable global prefix selection and owner-sharded full-space basis."""

    def __init__(self, definitions: tuple[TraceHarmonicDefinition, ...]) -> None:
        ordered_definitions = _ordered_slab_definitions(definitions)
        self._definitions = ordered_definitions
        self.comm = ordered_definitions[0].topology.mesh.comm
        row_support = _owned_row_slab_masks(
            ordered_definitions[0], ordered_definitions[0].mpc.function_space
        )
        slabs: list[DistributedTraceHarmonicSlab] = []
        try:
            for item in ordered_definitions:
                slabs.append(
                    DistributedTraceHarmonicSlab(
                        item, slab_row_support=row_support[int(item.slab_id)]
                    )
                )
        except Exception:
            for slab in slabs:
                slab.destroy()
            raise
        self._slabs = tuple(slabs)
        self._z: np.ndarray | None = None
        self._candidate_order: tuple[tuple[float, int, int], ...] = ()
        self._audit: dict[str, Any] = {
            "construction_workspace_released": False
        }
        self._construction_workspace_released = False
        self._destroyed = False

    @property
    def columns(self) -> np.ndarray:
        if self._z is None:
            raise RuntimeError("distributed trace basis has not been built")
        view = self._z.view()
        view.flags.writeable = False
        return view

    @property
    def candidate_order(self) -> tuple[tuple[float, int, int], ...]:
        return self._candidate_order

    @property
    def audit(self) -> Mapping[str, Any]:
        return MappingProxyType(self._audit)

    def _orthogonalize_column_in_place(self, column_index: int) -> None:
        column = self._z[:, int(column_index)]
        for _pass in range(2):
            for previous_index in range(int(column_index)):
                previous = self._z[:, previous_index]
                coefficient = self.comm.allreduce(
                    np.vdot(previous, column), op=MPI.SUM
                )
                column -= coefficient * previous
        norm_squared = float(
            self.comm.allreduce(np.vdot(column, column).real, op=MPI.SUM)
        )
        if not np.isfinite(norm_squared) or norm_squared <= 1.0e-28:
            raise RuntimeError("distributed trace columns are linearly dependent")
        column /= np.sqrt(norm_squared)

    def build(
        self,
        rank: int = D2_MAX_EIGENPAIRS,
        *,
        requested_eigenpairs: int = D2_MAX_EIGENPAIRS,
    ) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("distributed trace basis has been destroyed")
        if self._construction_workspace_released:
            raise RuntimeError("cannot build after construction workspace release")
        if int(rank) < 1 or int(rank) > D2_MAX_EIGENPAIRS:
            raise ValueError("basis rank must be in 1..64")
        self._z = None
        self._candidate_order = ()
        eigenvalues: list[tuple[float, int, int]] = []
        slab_vectors: dict[tuple[int, int], PETSc.Vec] = {}
        solved: list[tuple[tuple[tuple[float, int], ...], tuple[PETSc.Vec, ...]]] = []
        try:
            for slab in self._slabs:
                values, vectors = slab.solve_eigenpairs(
                    requested_eigenpairs=requested_eigenpairs
                )
                solved.append((values, vectors))
                eigenvalues.extend(
                    (float(value), slab.slab_id, int(local_index))
                    for value, local_index in values
                )
            eigenvalues.sort(key=lambda item: (item[0], item[1], item[2]))
            if len(eigenvalues) < int(rank):
                raise RuntimeError(
                    "requested basis rank exceeds merged eigenpair count"
                )
            selected = tuple(eigenvalues[: int(rank)])
            self._candidate_order = selected
            for _value, slab_id, local_index in selected:
                vectors = solved[slab_id][1]
                slab_vectors[(slab_id, local_index)] = vectors[local_index]

            self._z = np.empty(
                (self._slabs[0]._owned_rows, len(selected)),
                dtype=np.complex128,
                order="C",
            )
            for column_index, (_value, slab_id, local_index) in enumerate(
                selected
            ):
                slab = self._slabs[slab_id]
                vector = slab_vectors[(slab_id, local_index)]
                extension = slab._extend(vector)
                try:
                    self._z[:, column_index] = extension.getArray(
                        readonly=True
                    )[: slab._owned_rows]
                    self._z[slab.trace_rows, column_index] *= (
                        D2_SHARED_TRACE_WEIGHT
                    )
                finally:
                    extension.destroy()
                self._orthogonalize_column_in_place(column_index)
            self._z.flags.writeable = False
            scratch_local = int(
                self._z.shape[0] * np.dtype(np.complex128).itemsize
            )
            self._audit = {
                "schema": "fullspace.trace-harmonic-distributed.v1",
                "profile": D2_PROFILE,
                "slab_problem": "independent_K_i_q_lambda_M_Gamma_i_q",
                "candidate_order": "lambda_slab_id_local_index",
                "rank_prefix": int(rank),
                "rank_ladder": list(D2_RANK_PREFIXES),
                "shared_trace_weight": D2_SHARED_TRACE_WEIGHT,
                "restriction_prolongation": "owner_active_rows_unit_weight_euclidean",
                "phase_application": "finalized_floquet_mpc_once",
                "phase_anchor": "minimum_nonzero_harmonic_full_fe_packet",
                "physical_action_applied": False,
                "az_e_not_built": True,
                "numeric_allgather": False,
                "row_slab_metadata_collective": "owner_range_metadata_alltoall",
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "factor_materialized": False,
                "retained_z_bytes_local": int(self._z.nbytes),
                "retained_z_bytes_global": int(
                    self.comm.allreduce(self._z.nbytes, op=MPI.SUM)
                ),
                "orthogonalization_scratch_bytes_local": scratch_local,
                "orthogonalization_scratch_bytes_global_max": int(
                    self.comm.allreduce(scratch_local, op=MPI.MAX)
                ),
                "orthogonalization_scratch_bytes_global_sum": int(
                    self.comm.allreduce(scratch_local, op=MPI.SUM)
                ),
                "orthogonalization_scratch_is_in_place": True,
                "orthogonalization_scratch_bytes_provenance": (
                    "exact_array_size_derived_upper_bound"
                ),
                "trace_eigen_workspace_bytes": "derived_from_SLEPc_ncv_not_measured",
                "full_vector_transient_count": "not_measured",
                "unknown_python_jit_bytes": "not_measured",
                "slab_eigen_audits": tuple(
                    dict(slab._eigen_audit) for slab in self._slabs
                ),
                "construction_workspace_released": False,
            }
            return self.columns
        except Exception:
            self._z = None
            raise
        finally:
            for vectors in slab_vectors.values():
                vectors.destroy()
            for _values, vectors in solved:
                for vector in vectors:
                    if not any(vector is item for item in slab_vectors.values()):
                        vector.destroy()

    def release_construction_workspace(self) -> None:
        """Release slab assembly/KSP state while retaining the owner-local Z."""

        if self._destroyed:
            raise RuntimeError("distributed trace basis has been destroyed")
        if self._construction_workspace_released:
            raise RuntimeError("construction workspace has already been released")
        if self._z is None or len(self._audit["slab_eigen_audits"]) != 2:
            raise RuntimeError("release requires a successfully built basis")
        for slab in self._slabs:
            slab.destroy()
        self._slabs = ()
        self._definitions = ()
        self._construction_workspace_released = True
        self._audit["construction_workspace_released"] = True

    def fill_column(self, index: int, vector: PETSc.Vec) -> None:
        if self._z is None or int(index) < 0 or int(index) >= self._z.shape[1]:
            raise IndexError("basis column index is outside the retained prefix")
        values = vector.getArray()
        values[:] = 0.0
        values[:] = self._z[:, int(index)]
        vector.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._z = None
        for slab in self._slabs:
            slab.destroy()
        self._slabs = ()
        self._definitions = ()


def build_distributed_trace_harmonic_basis(
    definitions: tuple[TraceHarmonicDefinition, ...],
    *,
    rank: int = D2_MAX_EIGENPAIRS,
    requested_eigenpairs: int = D2_MAX_EIGENPAIRS,
) -> DistributedTraceHarmonicBasis:
    """Construct one fixed rank-prefix owner-sharded basis."""

    basis = DistributedTraceHarmonicBasis(definitions)
    try:
        basis.build(rank=rank, requested_eigenpairs=requested_eigenpairs)
        return basis
    except Exception:
        basis.destroy()
        raise


__all__ = (
    "D2_EPS_MAX_IT",
    "D2_EPS_TOL",
    "D2_KSP_MAX_IT",
    "D2_KSP_RTOL",
    "D2_MAX_EIGENPAIRS",
    "D2_PROFILE",
    "D2_RANK_PREFIXES",
    "D2_SHARED_TRACE_WEIGHT",
    "DistributedTraceHarmonicBasis",
    "DistributedTraceHarmonicSlab",
    "build_distributed_trace_harmonic_basis",
)
