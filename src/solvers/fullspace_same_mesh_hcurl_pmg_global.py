"""Small same-mesh p3-to-p1 H(curl) positive candidate.

The candidate is deliberately narrower than the closed LOR routes: both
matrices live on the same physical mesh, the fine p3 matrix is assembled only
for this small candidate, and the existing owner-local Basix transfer supplies
the two matrix-free transfer actions.  This module owns reusable V-cycle work
vectors, but not caller-owned matrices or the owner transfer.
"""

from __future__ import annotations

from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .fullspace_lor_edge_geometric_mg_global import FixedChebyshevJacobiPETSc
from .fullspace_lor_hx_root_cause import (
    DiagnosticDirectSolver,
    M0_DIRECT_BACKEND,
)


SAME_MESH_PMG_SCHEMA = "task038.same_mesh_hcurl_pmg.global.v1"
SAME_MESH_PMG_METHOD = "same_mesh_hcurl_pmg_v1"
SAME_MESH_PMG_LEVELS = (3, 1)
SAME_MESH_PMG_PAIR = (3, 1)
CHEBYSHEV_DEGREE = 3
POWER_STEPS = 10
PRE_COUNT = 1
POST_COUNT = 1
ADJOINT_LIMIT = 1.0e-11
LINEARITY_LIMIT = 1.0e-12
REPEAT_LIMIT = 1.0e-13
SAME_MESH_STRUCTURE_SEED = "task038.v13.c1.same-mesh-structure-v1"


def _matrix_size(matrix: Any, name: str) -> int:
    rows, columns = (int(value) for value in matrix.getSize())
    if rows <= 0 or rows != columns:
        raise ValueError(f"{name} matrix must be nonempty and square")
    return rows


def _matrix_local_shape(matrix: Any, name: str) -> tuple[int, int]:
    local_rows, local_columns = (int(value) for value in matrix.getLocalSize())
    if local_rows <= 0 or local_columns <= 0:
        raise ValueError(f"{name} matrix has an empty local layout")
    return local_rows, local_columns


def _matrix_hermitian_probe(matrix: Any, tolerance: float) -> bool:
    """Run an additional two-vector work diagnostic on SeqAIJ or MPIAIJ."""

    left = matrix.createVecRight()
    right = matrix.createVecRight()
    left_action = matrix.createVecLeft()
    right_action = matrix.createVecLeft()
    try:
        start, stop = left.getOwnershipRange()
        indices = np.arange(start, stop, dtype=np.float64)
        left.array[:] = (indices + 1.0) + 1j * (indices + 0.25)
        right.array[:] = (2.0 * indices + 0.5) - 1j * (indices + 1.5)
        matrix.mult(left, left_action)
        matrix.mult(right, right_action)
        lhs = complex(right.dot(left_action))
        rhs = complex(right_action.dot(left))
        relative = abs(lhs - rhs) / max(
            abs(lhs), abs(rhs), np.finfo(np.float64).tiny
        )
        return bool(np.isfinite(relative) and relative <= tolerance)
    finally:
        left.destroy()
        right.destroy()
        left_action.destroy()
        right_action.destroy()


def _matrix_hermitian_defect(matrix: Any) -> float:
    """Return the normalized Frobenius defect of a small sparse matrix."""

    hermitian = PETSc.Mat()
    difference = None
    try:
        matrix.hermitianTranspose(hermitian)
        difference = matrix.copy()
        difference.axpy(
            PETSc.ScalarType(-1.0),
            hermitian,
            structure=PETSc.Mat.Structure.DIFFERENT_NONZERO_PATTERN,
        )
        numerator = float(difference.norm(PETSc.NormType.FROBENIUS))
        denominator = max(
            float(matrix.norm(PETSc.NormType.FROBENIUS)),
            np.finfo(np.float64).tiny,
        )
        return numerator / denominator
    finally:
        if difference is not None:
            difference.destroy()
        hermitian.destroy()


def _vector_norm(vector: Any) -> float:
    value = float(vector.norm())
    if not np.isfinite(value):
        raise RuntimeError("same-mesh p3/p1 vector norm is non-finite")
    return value


def assemble_same_mesh_positive_matrix(
    space: Any,
    floquet: Any,
    *,
    curl_coefficient: Any,
    mass_coefficient: Any,
) -> PETSc.Mat:
    """Assemble one same-mesh positive H(curl) matrix with an existing MPC.

    This is the only assembly helper in the candidate.  The caller supplies
    the material coefficients from the existing tagged mesh; no LOR mesh,
    high-order global matrix, transfer matrix, or physical/DtN term is built.
    """

    if getattr(floquet, "mpc", None) is None:
        raise ValueError("same-mesh positive assembly requires a finalized MPC")
    import ufl
    from dolfinx import fem
    import dolfinx_mpc

    form = same_mesh_positive_form(
        space,
        curl_coefficient=curl_coefficient,
        mass_coefficient=mass_coefficient,
    )
    matrix = dolfinx_mpc.assemble_matrix(
        fem.form(form), floquet.mpc, bcs=[]
    )
    matrix.assemble()
    return matrix


def same_mesh_positive_form(
    space: Any,
    *,
    curl_coefficient: Any,
    mass_coefficient: Any,
) -> Any:
    """Return the fixed same-mesh curl-plus-mass UFL form."""

    import ufl

    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    return (
        curl_coefficient * ufl.inner(ufl.curl(trial), ufl.curl(test))
        + mass_coefficient * ufl.inner(trial, test)
    ) * ufl.dx


def _same_mesh_level_config(cfg: Any, degree: int) -> Any:
    if int(degree) == int(cfg.nedelec_degree):
        return cfg
    import copy

    level_cfg = copy.deepcopy(cfg)
    level_cfg.nedelec_degree = int(degree)
    level_cfg.visualization_degree = int(degree)
    level_cfg.nedelec_trace_degree = None
    level_cfg.nedelec_interior_degree = None
    level_cfg.case_name = f"{cfg.case_name}_same_mesh_p{int(degree)}"
    return level_cfg


def _build_same_mesh_levels(
    cfg: Any, comm: Any, degrees: tuple[int, ...]
) -> dict[str, Any]:
    """Build one physical mesh and the requested same-mesh N1curl levels."""

    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import (
        _mark_boundary_facets,
        _mark_cells,
        _stage4_axis_plan,
        _structured_hexa_mesh,
    )
    from .fullspace_lor_native_hx_fixture import _piecewise_positive_coefficients

    plan = _stage4_axis_plan(cfg, comm.size)
    mesh = _structured_hexa_mesh(
        comm,
        plan.x_values,
        plan.y_values,
        plan.z_values,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
    )
    facet_tags, _ = _mark_boundary_facets(mesh, cfg)
    cell_tags = _mark_cells(mesh, cfg)
    mesh_data = SimpleNamespace(
        mesh=mesh, cell_tags=cell_tags, facet_tags=facet_tags
    )
    spaces: dict[int, Any] = {}
    floquets: dict[int, Any] = {}
    for degree in degrees:
        degree = int(degree)
        space = fem.functionspace(
            mesh,
            element("N1curl", mesh.basix_cell(), degree, dtype=default_real_type),
        )
        spaces[degree] = space
        floquets[degree] = build_double_floquet_mpc(
            space, mesh_data, _same_mesh_level_config(cfg, degree)
        )
    mu, mass, coefficient_audit = _piecewise_positive_coefficients(
        mesh, cell_tags, cfg
    )
    return {
        "mesh": mesh,
        "mesh_data": mesh_data,
        "spaces": spaces,
        "floquets": floquets,
        "mu": mu,
        "mass": mass,
        "coefficient_audit": coefficient_audit,
    }


def build_small_same_mesh_positive_case(
    cfg: Any,
    comm: Any,
    *,
    source_name: str = "random",
) -> dict[str, Any]:
    """Build the reviewed p3/h50 same-mesh positive candidate.

    Mesh, tags, and both Floquet MPCs are made on one physical mesh.  The
    returned dictionary is an explicit ownership bundle for a focused runner;
    callers must destroy the vectors, matrices, and PMG object when finished.
    """

    if int(cfg.nedelec_degree) != 3 or float(cfg.mesh_target_size) != 50.0:
        raise ValueError("small same-mesh candidate is fixed at p3/h50")
    if source_name not in {"random", "gradient", "curl", "checkerboard"}:
        raise ValueError("unsupported frozen same-mesh source")

    from .fullspace_lor_native_hx_fixture import build_frozen_fullspace_primal_source
    from .fullspace_same_mesh_hcurl_pmg_runtime import (
        build_same_mesh_hcurl_owner_transfer,
    )
    from .fullspace_same_mesh_hcurl_pmg import (
        build_same_mesh_hcurl_transfer,
    )
    from .fullspace_mpc_action import build_fullspace_mpc_form_action

    levels = _build_same_mesh_levels(cfg, comm, (3, 1))
    mesh = levels["mesh"]
    mesh_data = levels["mesh_data"]
    fine_space = levels["spaces"][3]
    coarse_space = levels["spaces"][1]
    fine_floquet = levels["floquets"][3]
    coarse_floquet = levels["floquets"][1]
    mu = levels["mu"]
    mass = levels["mass"]
    coefficient_audit = levels["coefficient_audit"]
    fine_matrix = assemble_same_mesh_positive_matrix(
        fine_space,
        fine_floquet,
        curl_coefficient=mu,
        mass_coefficient=mass,
    )
    coarse_matrix = assemble_same_mesh_positive_matrix(
        coarse_space,
        coarse_floquet,
        curl_coefficient=mu,
        mass_coefficient=mass,
    )
    fine_action = build_fullspace_mpc_form_action(
        same_mesh_positive_form(
            fine_space, curl_coefficient=mu, mass_coefficient=mass
        ),
        fine_space,
        mpc=fine_floquet.mpc,
    )
    local_transfer = build_same_mesh_hcurl_transfer(3, 1)
    owner_transfer = build_same_mesh_hcurl_owner_transfer(
        fine_space,
        fine_floquet,
        coarse_space,
        coarse_floquet,
        local_transfer=local_transfer,
    )
    source, source_facts = build_frozen_fullspace_primal_source(
        fine_space, fine_floquet, cfg, source_name
    )
    algebraic_source = _algebraic_fine_function(
        source, fine_floquet.mpc.function_space, fine_floquet
    )
    rhs = fine_matrix.createVecLeft()
    fine_matrix.mult(algebraic_source.x.petsc_vec, rhs)
    del algebraic_source
    pmg = SameMeshHcurlPmg(
        fine_matrix,
        coarse_matrix,
        owner_transfer,
        owns_owner_transfer=True,
    )
    return {
        "mesh": mesh,
        "mesh_data": mesh_data,
        "fine_space": fine_space,
        "coarse_space": coarse_space,
        "fine_floquet": fine_floquet,
        "coarse_floquet": coarse_floquet,
        "fine_matrix": fine_matrix,
        "coarse_matrix": coarse_matrix,
        "fine_action": fine_action,
        "owner_transfer": owner_transfer,
        "local_transfer": local_transfer,
        "pmg": pmg,
        "source": source,
        "rhs": rhs,
        "source_facts": source_facts,
        "coefficient_audit": coefficient_audit,
    }


def destroy_small_same_mesh_positive_case(case: dict[str, Any]) -> None:
    """Release the explicit resources returned by the small case builder."""

    pmg = case.pop("pmg", None)
    if pmg is not None:
        pmg.destroy()
    for name in ("source", "rhs"):
        vector = case.pop(name, None)
        if vector is not None:
            vector.destroy()
    action = case.pop("fine_action", None)
    if action is not None:
        action.destroy()
    for name in ("fine_matrix", "coarse_matrix"):
        matrix = case.pop(name, None)
        if matrix is not None:
            matrix.destroy()
    owner = case.pop("owner_transfer", None)
    if owner is not None and pmg is None:
        owner.destroy()
    case.pop("fine_floquet", None)
    case.pop("coarse_floquet", None)


def _vector_relative(left: Any, right: Any) -> float:
    difference = left.copy()
    try:
        difference.axpy(-1.0, right)
        numerator = _vector_norm(difference)
    finally:
        difference.destroy()
    return numerator / max(_vector_norm(right), np.finfo(np.float64).tiny)


def _algebraic_fine_function(vector: Any, space: Any, floquet: Any) -> Any:
    """Copy a full primal vector and finalize its slave-zero algebraic view."""

    from dolfinx import fem

    field = fem.Function(space)
    vector.copy(field.x.petsc_vec)
    field.x.scatter_forward()
    floquet.mpc.homogenize(field)
    field.x.scatter_forward()
    return field


def audit_small_same_mesh_structure(case: Mapping[str, Any]) -> dict[str, Any]:
    """Measure the bounded global probe and the assembled/form-action identity."""

    from .hcurl_canonical_vector_dolfinx import (
        build_physical_canonical_primal_source,
    )
    from .fullspace_same_mesh_hcurl_pmg_runtime import (
        _finite_global,
        _mpc_constraint_residual,
        _slave_storage_max,
    )
    from dolfinx import fem

    fine_matrix = case["fine_matrix"]
    coarse_matrix = case["coarse_matrix"]
    owner_transfer = case["owner_transfer"]
    form_action = case["fine_action"]
    coarse_probe = coarse_matrix.createVecRight()
    canonical_source = None
    fine_probe = fine_repeat = fine_action = form_output = None
    fine_full = fine_algebraic = None
    coarse_direct = coarse_restricted = None
    try:
        canonical_source, source_facts = build_physical_canonical_primal_source(
            case["coarse_space"],
            case["coarse_floquet"],
            fixed_seed=SAME_MESH_STRUCTURE_SEED,
        )
        canonical_source.x.scatter_forward()
        case["coarse_floquet"].mpc.homogenize(canonical_source)
        canonical_source.x.scatter_forward()
        canonical_source.x.petsc_vec.copy(coarse_probe)
        probe_before = np.asarray(coarse_probe.array).copy()
        fine_probe = owner_transfer.apply_primal(coarse_probe)
        fine_repeat = owner_transfer.apply_primal(coarse_probe)
        fine_mpc_space = owner_transfer.fine_floquet.mpc.function_space
        fine_full = fem.Function(fine_mpc_space)
        fine_probe.copy(fine_full.x.petsc_vec)
        fine_full.x.scatter_forward()
        full_constraint = _mpc_constraint_residual(
            fine_full, case["fine_floquet"]
        )
        fine_algebraic = _algebraic_fine_function(
            fine_probe, fine_mpc_space, case["fine_floquet"]
        )
        algebraic_slave_max = _slave_storage_max(
            fine_algebraic, case["fine_floquet"]
        )
        fine_action = fine_matrix.createVecLeft()
        fine_matrix.mult(fine_algebraic.x.petsc_vec, fine_action)
        form_output = fine_matrix.createVecLeft()
        borrowed = form_action.apply(fine_algebraic.x.petsc_vec)
        borrowed.copy(form_output)
        coarse_restricted = owner_transfer.apply_adjoint(fine_action)
        coarse_direct = coarse_matrix.createVecLeft()
        coarse_matrix.mult(coarse_probe, coarse_direct)
        lhs = complex(fine_algebraic.x.petsc_vec.dot(fine_action))
        rhs = complex(coarse_probe.dot(coarse_restricted))
        gal_energy = complex(lhs)
        direct_energy = complex(coarse_probe.dot(coarse_direct))
        probe_norm = _vector_norm(coarse_probe)
        fine_norm = _vector_norm(fine_algebraic.x.petsc_vec)
        comm = coarse_probe.getComm().tompi4py()
        source_finite = bool(
            comm.allreduce(
                int(np.all(np.isfinite(np.asarray(coarse_probe.array)))),
                op=MPI.MIN,
            )
        )
        projected_finite = bool(
            comm.allreduce(
                int(np.all(np.isfinite(np.asarray(fine_probe.array)))),
                op=MPI.MIN,
            )
        )
        source_unchanged = bool(
            comm.allreduce(
                int(np.array_equal(np.asarray(coarse_probe.array), probe_before)),
                op=MPI.MIN,
            )
        )
        fine_hermitian_defect = _matrix_hermitian_defect(fine_matrix)
        coarse_hermitian_defect = _matrix_hermitian_defect(coarse_matrix)
        fine_hermitian_work_probe = _matrix_hermitian_probe(
            fine_matrix, 1.0e-12
        )
        coarse_hermitian_work_probe = _matrix_hermitian_probe(
            coarse_matrix, 1.0e-12
        )
        return {
            "source": dict(source_facts),
            "source_finite": source_finite,
            "source_nonzero": bool(comm.allreduce(int(probe_norm > 0.0), op=MPI.LOR)),
            "source_input_unchanged": source_unchanged,
            "full_primal_constraint_residual": float(full_constraint),
            "full_primal_slave_storage_max": _slave_storage_max(
                fine_full, case["fine_floquet"]
            ),
            "algebraic_slave_storage_max": float(algebraic_slave_max),
            "projected_full_finite": _finite_global(
                np.asarray(fine_full.x.array), comm
            ),
            "projected_finite": projected_finite,
            "projected_repeat_relative": _vector_relative(
                fine_repeat, fine_probe
            ),
            "assembled_form_action_relative": _vector_relative(
                form_output, fine_action
            ),
            "global_adjoint_work_relative": float(
                abs(lhs - rhs)
                / max(abs(rhs), np.finfo(np.float64).tiny)
            ),
            "galerkin_action_relative": _vector_relative(
                coarse_restricted, coarse_direct
            ),
            "galerkin_energy_relative": float(
                abs(gal_energy - direct_energy)
                / max(abs(direct_energy), np.finfo(np.float64).tiny)
            ),
            "fine_probe_norm": fine_norm,
            "coarse_probe_norm": probe_norm,
            "coarse_energy": [direct_energy.real, direct_energy.imag],
            "galerkin_energy": [gal_energy.real, gal_energy.imag],
            "fine_matrix_hermitian_defect": float(fine_hermitian_defect),
            "coarse_matrix_hermitian_defect": float(coarse_hermitian_defect),
            "fine_matrix_hermitian_work_probe": fine_hermitian_work_probe,
            "coarse_matrix_hermitian_work_probe": coarse_hermitian_work_probe,
            "fine_matrix_hermitian": bool(
                np.isfinite(fine_hermitian_defect)
                and fine_hermitian_defect <= 1.0e-12
            ),
            "coarse_matrix_hermitian": bool(
                np.isfinite(coarse_hermitian_defect)
                and coarse_hermitian_defect <= 1.0e-12
            ),
            "finite": bool(
                comm.allreduce(
                    int(
                        np.isfinite(lhs)
                        and np.isfinite(rhs)
                        and np.isfinite(direct_energy)
                        and np.isfinite(gal_energy)
                    ),
                    op=MPI.MIN,
                )
            ),
        }
    finally:
        for vector in (
            coarse_probe,
            fine_probe,
            fine_repeat,
            fine_action,
            form_output,
            coarse_direct,
            coarse_restricted,
        ):
            if vector is not None:
                vector.destroy()
        # These are dolfinx Functions; their PETSc storage is owned by the
        # Function and is released by Python object lifetime, not Vec.destroy.
        del fine_full, fine_algebraic, canonical_source


def _transfer_audit(transfer: Any) -> Mapping[str, Any]:
    audit = getattr(transfer, "audit", None)
    if not isinstance(audit, Mapping):
        raise ValueError("same-mesh PMG requires owner-transfer audit facts")
    if tuple(audit.get("pair_fine_to_coarse", ())) != SAME_MESH_PMG_PAIR:
        raise ValueError("same-mesh PMG requires the fixed p3-to-p1 transfer")
    for key in ("fine_global_rows", "coarse_global_rows"):
        if key not in audit:
            raise ValueError(f"owner transfer audit is missing {key}")
    return audit


class SameMeshHcurlPmg:
    """One fixed p3 -> p1 same-mesh V-cycle action.

    ``apply`` maps a fine-space residual (dual storage) to one fine-space
    primal correction.  The transfer and matrices are supplied by the caller;
    smoother, the p1 direct oracle, and work vectors are owned here unless a
    focused test injects counted replacements.
    """

    def __init__(
        self,
        fine_matrix: Any,
        coarse_matrix: Any,
        owner_transfer: Any,
        *,
        smoother: Any | None = None,
        coarse_solver: Any | None = None,
        owns_owner_transfer: bool = False,
    ) -> None:
        fine_size = _matrix_size(fine_matrix, "fine")
        coarse_size = _matrix_size(coarse_matrix, "coarse")
        fine_local_rows, fine_local_columns = _matrix_local_shape(
            fine_matrix, "fine"
        )
        coarse_local_rows, coarse_local_columns = _matrix_local_shape(
            coarse_matrix, "coarse"
        )
        transfer_audit = _transfer_audit(owner_transfer)
        for key, expected in (
            ("fine_global_rows", fine_size),
            ("coarse_global_rows", coarse_size),
        ):
            if int(transfer_audit[key]) != expected:
                raise ValueError(f"owner transfer {key} does not match matrix")
        self.fine_matrix = fine_matrix
        self.coarse_matrix = coarse_matrix
        self.owner_transfer = owner_transfer
        self._owns_owner_transfer = bool(owns_owner_transfer)
        self._owns_smoother = smoother is None
        self._owns_coarse_solver = coarse_solver is None
        self._fine_rhs_layout = (fine_size, fine_local_rows)
        self._fine_target_layout = (fine_size, fine_local_columns)
        self._coarse_rhs_layout = (coarse_size, coarse_local_rows)
        self._coarse_target_layout = (coarse_size, coarse_local_columns)
        fine_mpc = getattr(owner_transfer.fine_floquet, "mpc", None)
        if fine_mpc is None:
            raise ValueError("same-mesh PMG requires the fine Floquet MPC")
        fine_slaves = np.asarray(fine_mpc.slaves, dtype=np.int64)
        fine_index_map = fine_mpc.function_space.dofmap.index_map
        fine_storage = int(fine_index_map.size_local + fine_index_map.num_ghosts)
        if fine_slaves.size and (
            np.any(fine_slaves < 0) or np.any(fine_slaves >= fine_storage)
        ):
            raise ValueError("fine MPC slave rows exceed local storage")
        if np.unique(fine_slaves).size != fine_slaves.size:
            raise ValueError("fine MPC slave rows are duplicated")
        self._fine_owned_slave_indices = np.ascontiguousarray(
            fine_slaves[fine_slaves < fine_local_rows], dtype=np.int32
        ).copy()
        self._fine_owned_slave_indices.flags.writeable = False
        self._destroyed = False
        self.apply_count = 0
        self._transfer_counts = {"primal": 0, "adjoint": 0}
        self._smoother_apply_total = 0
        self._p1_solve_total = 0
        self.max_p1_relative_residual = 0.0

        self.smoother = (
            FixedChebyshevJacobiPETSc(fine_matrix)
            if smoother is None
            else smoother
        )
        self.coarse_solver = (
            DiagnosticDirectSolver(
                coarse_matrix, label="same-mesh-p1-exact-oracle"
            )
            if coarse_solver is None
            else coarse_solver
        )
        self._work: list[Any] = []
        try:
            self._allocate_work()
            self.audit = MappingProxyType(
                {
                    "schema": SAME_MESH_PMG_SCHEMA,
                    "method": SAME_MESH_PMG_METHOD,
                    "levels": list(SAME_MESH_PMG_LEVELS),
                    "pairs": [list(SAME_MESH_PMG_PAIR)],
                    "fine_degree": 3,
                    "coarse_degree": 1,
                    "fine_owned_mpc_slave_count": int(
                        self._fine_owned_slave_indices.size
                    ),
                    "fine_matrix_rows": fine_size,
                    "coarse_matrix_rows": coarse_size,
                    "small_only": True,
                    "p3_sparse_allowed": True,
                    "p6_global_aij": False,
                    "lor_mesh": False,
                    "global_high_order_aij": False,
                    "global_dense_transfer": False,
                    "global_transfer_matrix": False,
                    "numeric_allgather": False,
                    "hx_hierarchy_built": False,
                    "pcgamg_hierarchy_built": False,
                    "physical_solve": False,
                    "pde": False,
                    "physical": False,
                    "smoother": "fixed_degree_3_chebyshev_jacobi",
                    "smoother_instances": 1,
                    "power_steps": POWER_STEPS,
                    "pre_smoother_count": PRE_COUNT,
                    "post_smoother_count": POST_COUNT,
                    "p1_exact_factor": True,
                    "p1_exact_solver_backend": M0_DIRECT_BACKEND,
                    "p3_exact_factor": False,
                    "level1_factor": True,
                    "outer_ksp_created": False,
                    "coarse_direct_oracle": True,
                    "phase_application": "delegated_to_same_mesh_owner_transfer",
                    "owner_transfer_caller_owned": not self._owns_owner_transfer,
                    "retains_per_apply_history": False,
                    "destroy_order": [
                        "p1_factor",
                        "smoother",
                        "work_vectors",
                        "owner_transfer_if_owned",
                    ],
                }
            )
            self.last_apply_facts: dict[str, object] = {}
        except Exception:
            self.destroy()
            raise

    def _allocate_work(self) -> None:
        def right(matrix: Any) -> Any:
            vector = matrix.createVecRight()
            self._work.append(vector)
            return vector

        def left(matrix: Any) -> Any:
            vector = matrix.createVecLeft()
            self._work.append(vector)
            return vector

        self._fine_pre = right(self.fine_matrix)
        self._fine_action = left(self.fine_matrix)
        self._fine_residual = left(self.fine_matrix)
        self._fine_correction = right(self.fine_matrix)
        self._fine_solution = right(self.fine_matrix)
        self._fine_post_action = left(self.fine_matrix)
        self._fine_post_residual = left(self.fine_matrix)
        self._fine_post_correction = right(self.fine_matrix)
        self._coarse_rhs = left(self.coarse_matrix)
        self._coarse_solution = right(self.coarse_matrix)
        self._coarse_action = left(self.coarse_matrix)
        self._coarse_residual = left(self.coarse_matrix)

    @property
    def work_vectors(self) -> tuple[Any, ...]:
        """Return the reusable internal PETSc vectors for lifecycle audits."""

        return tuple(self._work)

    def _require_vector(
        self, vector: Any, layout: tuple[int, int], name: str
    ) -> None:
        expected_global, expected_local = layout
        if int(vector.getSize()) != expected_global:
            raise ValueError(f"{name} vector has an unexpected global size")
        if int(vector.getLocalSize()) != expected_local:
            raise ValueError(f"{name} vector has an unexpected local size")

    def _transfer_into(self, operation: str, source: Any, target: Any) -> None:
        if operation == "adjoint":
            self.owner_transfer.apply_adjoint_into(source, target)
        elif operation == "primal":
            self.owner_transfer.apply_primal_into(source, target)
        else:
            raise ValueError(f"unknown same-mesh transfer operation {operation!r}")
        self._transfer_counts[operation] += 1

    def _zero_owned_fine_slaves(self, vector: Any) -> None:
        if self._fine_owned_slave_indices.size:
            vector.array[self._fine_owned_slave_indices] = 0.0

    def _owned_slave_max(self, vector: Any) -> float:
        local = (
            float(
                np.max(np.abs(vector.array[self._fine_owned_slave_indices]))
            )
            if self._fine_owned_slave_indices.size
            else 0.0
        )
        comm = self.fine_matrix.getComm().tompi4py()
        return float(comm.allreduce(local, op=MPI.MAX))

    def apply_into(self, rhs: Any, target: Any) -> dict[str, object]:
        """Apply the fixed two-level cycle into an existing fine-space Vec."""

        if self._destroyed:
            raise RuntimeError("same-mesh p3/p1 PMG has been destroyed")
        self._require_vector(rhs, self._fine_rhs_layout, "fine residual")
        self._require_vector(target, self._fine_target_layout, "fine target")
        order: list[str] = []

        self.smoother.apply_into(rhs, self._fine_pre)
        self._smoother_apply_total += 1
        order.append("p3_pre")
        self.fine_matrix.mult(self._fine_pre, self._fine_action)
        rhs.copy(self._fine_residual)
        self._fine_residual.axpy(-1.0, self._fine_action)

        self._transfer_into("adjoint", self._fine_residual, self._coarse_rhs)
        order.append("p3_to_p1_adjoint")
        solution, solve_facts = self.coarse_solver.solve_lean(self._coarse_rhs)
        try:
            solution.copy(self._coarse_solution)
        finally:
            solution.destroy()
        self._p1_solve_total += 1
        order.append("p1_exact")

        self.coarse_matrix.mult(self._coarse_solution, self._coarse_action)
        self._coarse_rhs.copy(self._coarse_residual)
        self._coarse_residual.axpy(-1.0, self._coarse_action)
        coarse_norm = _vector_norm(self._coarse_rhs)
        p1_relative = _vector_norm(self._coarse_residual) / max(
            coarse_norm, np.finfo(np.float64).tiny
        )
        if not np.isfinite(p1_relative):
            raise RuntimeError("same-mesh p1 residual is non-finite")

        self._transfer_into("primal", self._coarse_solution, self._fine_correction)
        order.append("p1_to_p3_primal")
        self._zero_owned_fine_slaves(self._fine_correction)
        self._fine_pre.copy(self._fine_solution)
        self._fine_solution.axpy(1.0, self._fine_correction)

        self.fine_matrix.mult(self._fine_solution, self._fine_post_action)
        rhs.copy(self._fine_post_residual)
        self._fine_post_residual.axpy(-1.0, self._fine_post_action)
        self.smoother.apply_into(
            self._fine_post_residual, self._fine_post_correction
        )
        self._smoother_apply_total += 1
        self._fine_solution.axpy(1.0, self._fine_post_correction)
        self._zero_owned_fine_slaves(self._fine_solution)
        order.append("p3_post")
        self._fine_solution.copy(target)

        output_norm = _vector_norm(target)
        owned_slave_max = self._owned_slave_max(target)
        if not np.isfinite(owned_slave_max) or owned_slave_max != 0.0:
            raise RuntimeError("same-mesh PMG output is not algebraic slave-zero")
        self.apply_count += 1
        self.max_p1_relative_residual = max(
            self.max_p1_relative_residual, float(p1_relative)
        )
        facts: dict[str, object] = {
            "order": tuple(order),
            "pre_smoother_count": 1,
            "post_smoother_count": 1,
            "transfer_3_1_adjoint_count": 1,
            "transfer_3_1_primal_count": 1,
            "smoother_apply_count": 2,
            "smoother_apply_total": int(self._smoother_apply_total),
            "p1_solve_count": 1,
            "p1_solve_total": int(self._p1_solve_total),
            "p1_relative_residual": float(p1_relative),
            "p1_solver_facts": dict(solve_facts),
            "output_finite": bool(np.isfinite(output_norm)),
            "owned_slave_max": owned_slave_max,
            "apply_count": int(self.apply_count),
            "transfer_3_1_adjoint_total": int(self._transfer_counts["adjoint"]),
            "transfer_3_1_primal_total": int(self._transfer_counts["primal"]),
        }
        if not facts["output_finite"]:
            raise RuntimeError("same-mesh p3/p1 output is non-finite")
        self.last_apply_facts = facts
        return facts

    def apply(self, rhs: Any) -> Any:
        """Return one new fine-space output; all other Vecs are reused."""

        if self._destroyed:
            raise RuntimeError("same-mesh p3/p1 PMG has been destroyed")
        output = self.fine_matrix.createVecRight()
        try:
            self.apply_into(rhs, output)
        except Exception:
            output.destroy()
            raise
        return output

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        coarse_solver = getattr(self, "coarse_solver", None)
        if self._owns_coarse_solver and coarse_solver is not None:
            coarse_solver.destroy()
        self.coarse_solver = None
        smoother = getattr(self, "smoother", None)
        if self._owns_smoother and smoother is not None:
            smoother.destroy()
        self.smoother = None
        for vector in getattr(self, "_work", ()):
            vector.destroy()
        self._work = []
        self._fine_owned_slave_indices = np.empty(0, dtype=np.int32)
        transfer = getattr(self, "owner_transfer", None)
        if self._owns_owner_transfer and transfer is not None:
            transfer.destroy()
        self.owner_transfer = None
        self.fine_matrix = None
        self.coarse_matrix = None


__all__ = [
    "ADJOINT_LIMIT",
    "CHEBYSHEV_DEGREE",
    "LINEARITY_LIMIT",
    "POST_COUNT",
    "POWER_STEPS",
    "PRE_COUNT",
    "REPEAT_LIMIT",
    "SAME_MESH_PMG_LEVELS",
    "SAME_MESH_PMG_METHOD",
    "SAME_MESH_PMG_PAIR",
    "SAME_MESH_PMG_SCHEMA",
    "SAME_MESH_STRUCTURE_SEED",
    "SameMeshHcurlPmg",
    "assemble_same_mesh_positive_matrix",
    "audit_small_same_mesh_structure",
    "build_small_same_mesh_positive_case",
    "destroy_small_same_mesh_positive_case",
    "same_mesh_positive_form",
]
