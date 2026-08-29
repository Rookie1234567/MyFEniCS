"""Ownership bundle and retained-ledger facts for the p6 same-mesh candidate.

The bundle is deliberately setup-only.  It builds one physical mesh with
same-mesh N1curl p6, p3, and p1 spaces, retains no source or outer KSP, and
connects the already reviewed p6 shell, owner-local transfers, and lower
p3-to-p1 development cycle.  It does not run a solve or create a restart
reserve.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .fullspace_lor_hx_root_cause import M0_DIRECT_BACKEND
from .fullspace_mpc_action import build_fullspace_mpc_form_action
from .fullspace_same_mesh_hcurl_pmg import build_same_mesh_hcurl_transfer
from .fullspace_same_mesh_hcurl_pmg_global import (
    SameMeshHcurlPmg,
    _build_same_mesh_levels,
    assemble_same_mesh_positive_matrix,
    same_mesh_positive_form,
)
from .fullspace_same_mesh_hcurl_pmg_p6 import (
    SameMeshP6MatrixFreeShell,
    SameMeshP6NestedVcycle,
    build_constrained_jacobi_diagonal,
)
from .fullspace_same_mesh_hcurl_pmg_runtime import (
    build_same_mesh_hcurl_owner_transfer,
)


P6_SETUP_SCHEMA = "task038.same_mesh_hcurl_pmg.setup.v1"
P6_SETUP_LEVELS = (6, 3, 1)
P6_SETUP_PAIRS = ((6, 3), (3, 1))
P6_SETUP_WAVELENGTH_NM = 13.5
P6_SETUP_MESH_TARGET_NM = 10.0
P6_SETUP_SCALAR_ITEMSIZE = int(np.dtype(PETSc.ScalarType).itemsize)
SAME_MESH_JIT_OPTIONS = MappingProxyType({})
_SMOOTHER_VECTOR_NAMES = (
    "_inv_sqrt",
    "_scaled_input",
    "_scaled_action",
    "_rhs_scaled",
    "_residual",
    "_direction",
    "_solution",
    "_action",
)


def validate_p6_setup_config(cfg: Any) -> None:
    """Require the one prospective 13.5 nm p6/h10 setup profile."""

    if int(cfg.nedelec_degree) != 6:
        raise ValueError("p6 setup requires nedelec_degree=6")
    if float(cfg.mesh_target_size) != P6_SETUP_MESH_TARGET_NM:
        raise ValueError("p6 setup requires mesh_target_size=10 nm")
    if float(cfg.lambda0) != P6_SETUP_WAVELENGTH_NM:
        raise ValueError("p6 setup requires wavelength=13.5 nm")


def _space_layout(space: Any) -> dict[str, int]:
    index_map = space.dofmap.index_map
    block_size = int(space.dofmap.index_map_bs)
    return {
        "global_rows": int(index_map.size_global) * block_size,
        "local_owned_rows": int(index_map.size_local) * block_size,
        "local_storage_entries": (
            int(index_map.size_local) + int(index_map.num_ghosts)
        )
        * block_size,
    }


def _reported_bytes(info: Mapping[str, Any]) -> int | None:
    value = info.get("memory")
    if value is None or not np.isfinite(float(value)) or float(value) <= 0.0:
        return None
    return int(value)


def _matrix_facts(matrix: Any) -> dict[str, Any]:
    rows, cols = (int(value) for value in matrix.getSize())
    local_rows, local_cols = (int(value) for value in matrix.getLocalSize())
    comm = matrix.getComm().tompi4py()
    info = matrix.getInfo(PETSc.Mat.InfoType.LOCAL)
    local_nnz = int(info["nz_used"]) if "nz_used" in info else None
    global_nnz = (
        None
        if local_nnz is None
        else int(comm.allreduce(local_nnz, op=MPI.SUM))
    )
    local_memory = _reported_bytes(info)
    global_memory = (
        None
        if local_memory is None
        else int(comm.allreduce(local_memory, op=MPI.SUM))
    )
    return {
        "rows": rows,
        "cols": cols,
        "local_rows": local_rows,
        "local_cols": local_cols,
        "global_nnz": global_nnz,
        "petsc_reported_memory_bytes": {
            "local": local_memory,
            "global": global_memory,
        },
    }


def _vector_bytes(vector: Any) -> int:
    return int(vector.getLocalSize()) * P6_SETUP_SCALAR_ITEMSIZE


def _local_form_bytes(vector: Any) -> int:
    with vector.localForm() as local:
        return int(local.array.nbytes)


def _work_facts(cycle: Any) -> dict[str, Any]:
    vectors = tuple(cycle.work_vectors)
    return {
        "count": len(vectors),
        "local_numeric_bytes": int(sum(_vector_bytes(vector) for vector in vectors)),
    }


def _smoother_facts(smoother: Any) -> dict[str, Any]:
    vectors = tuple(getattr(smoother, name) for name in _SMOOTHER_VECTOR_NAMES)
    return {
        "count": len(vectors),
        "local_numeric_bytes": int(sum(_vector_bytes(vector) for vector in vectors)),
    }


def _factor_facts(cycle: Any) -> dict[str, Any]:
    solver = cycle.coarse_solver
    comm = cycle.coarse_matrix.getComm().tompi4py()
    pc = solver.ksp.getPC()
    factor_getter = getattr(pc, "getFactorMatrix", None)
    factor = factor_getter() if callable(factor_getter) else None
    if factor is None:
        rows = nnz = local_memory = global_memory = None
    else:
        rows = int(factor.getSize()[0])
        info = factor.getInfo(PETSc.Mat.InfoType.LOCAL)
        local_nnz = int(info["nz_used"]) if "nz_used" in info else None
        nnz = (
            None
            if local_nnz is None
            else int(comm.allreduce(local_nnz, op=MPI.SUM))
        )
        local_memory = _reported_bytes(info)
        global_memory = (
            None
            if local_memory is None
            else int(comm.allreduce(local_memory, op=MPI.SUM))
        )
    return {
        "backend": M0_DIRECT_BACKEND,
        "factor_matrix_rows": rows,
        "factor_matrix_nnz": nnz,
        "petsc_reported_memory_available": local_memory is not None,
        "petsc_reported_memory_bytes": {
            "local": local_memory,
            "global": global_memory,
        },
        "setup_count": 1,
        "solve_count": int(solver.solve_count),
    }


def _transfer_facts(local_transfer: Any, owner_transfer: Any) -> dict[str, Any]:
    owner_audit = dict(owner_transfer.audit)
    local_audit = dict(local_transfer.audit)
    return {
        "local_audit": local_audit,
        "owner_audit": owner_audit,
        "local_cache_array_bytes": int(owner_audit["local_cache_array_bytes"]),
    }


def _p6_action_facts(shell: Any) -> dict[str, Any]:
    action_audit = dict(shell.action.audit)
    components = dict(action_audit["retained_numeric_payload_components"])
    return {
        "audit": action_audit,
        "retained_numeric_payload_components": components,
        "retained_numeric_payload_local_bytes": int(
            action_audit["retained_numeric_payload_local_bytes"]
        ),
        "retained_numeric_payload_global_sum_bytes": int(
            action_audit["retained_numeric_payload_global_sum_bytes"]
        ),
        "retained_numeric_payload_global_max_bytes": int(
            action_audit["retained_numeric_payload_global_max_bytes"]
        ),
    }


def _retained_ledger(
    bundle: Mapping[str, Any],
    matrices: Mapping[str, Any],
    transfers: Mapping[str, Any],
    action: Mapping[str, Any],
    work: Mapping[str, Any],
    smoothers: Mapping[str, Any],
    factor: Mapping[str, Any],
) -> dict[str, Any]:
    diagonal = bundle["p6_shell"].diagonal
    diagonal_local_bytes = _local_form_bytes(diagonal)
    diagonal_global_bytes = int(
        diagonal.getComm().tompi4py().allreduce(diagonal_local_bytes, op=MPI.SUM)
    )
    components: dict[str, int | None] = {
        "p6_action_retained_local_bytes": int(
            action["retained_numeric_payload_local_bytes"]
        ),
        "p6_exact_diagonal_local_numeric_bytes": diagonal_local_bytes,
        "p63_transfer_local_cache_array_bytes": int(
            transfers["p63"]["local_cache_array_bytes"]
        ),
        "p31_transfer_local_cache_array_bytes": int(
            transfers["p31"]["local_cache_array_bytes"]
        ),
        "upper_work_local_numeric_bytes": int(
            work["upper"]["local_numeric_bytes"]
        ),
        "lower_work_local_numeric_bytes": int(
            work["lower"]["local_numeric_bytes"]
        ),
        "upper_smoother_local_numeric_bytes": int(
            smoothers["upper"]["local_numeric_bytes"]
        ),
        "lower_smoother_local_numeric_bytes": int(
            smoothers["lower"]["local_numeric_bytes"]
        ),
        "p3_matrix_reported_memory_local_bytes": matrices["p3"][
            "petsc_reported_memory_bytes"
        ]["local"],
        "p1_matrix_reported_memory_local_bytes": matrices["p1"][
            "petsc_reported_memory_bytes"
        ]["local"],
        "p1_factor_reported_memory_local_bytes": factor[
            "petsc_reported_memory_bytes"
        ]["local"],
    }
    known = int(sum(value for value in components.values() if value is not None))
    return {
        "components_local_bytes": components,
        "global_facts": {
            "p6_exact_diagonal_global_numeric_bytes": diagonal_global_bytes,
        },
        "known_component_local_bytes": known,
        "unavailable_components": [
            name for name, value in components.items() if value is None
        ],
        "not_included": ["restart20_reserve", "outer_ksp", "source"],
        "semantics": "known/measured component ledger; unavailable values are not estimated",
    }


def build_p6_same_mesh_setup(
    cfg: Any, comm: Any = MPI.COMM_WORLD
) -> dict[str, Any]:
    """Build the fixed p6/p3/p1 setup bundle without a source or outer KSP."""

    validate_p6_setup_config(cfg)
    if int(comm.size) != 1:
        raise ValueError("p6 setup bundle is prospective MPI1 only")
    levels = _build_same_mesh_levels(cfg, comm, P6_SETUP_LEVELS)
    bundle: dict[str, Any] = {
        "schema": P6_SETUP_SCHEMA,
        **levels,
    }
    p6_action = None
    p6_diagonal = None
    try:
        spaces = bundle["spaces"]
        floquets = bundle["floquets"]
        mu = bundle["mu"]
        mass = bundle["mass"]
        p6_form = same_mesh_positive_form(
            spaces[6], curl_coefficient=mu, mass_coefficient=mass
        )
        p6_action = build_fullspace_mpc_form_action(
            p6_form,
            spaces[6],
            mpc=floquets[6].mpc,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        from dolfinx import fem

        p6_diagonal = build_constrained_jacobi_diagonal(
            fem.form(p6_form, jit_options=dict(SAME_MESH_JIT_OPTIONS)),
            floquets[6].mpc,
        )
        bundle["p6_shell"] = SameMeshP6MatrixFreeShell(
            p6_action, p6_diagonal
        )
        p6_action = None
        p6_diagonal = None

        bundle["p3_matrix"] = assemble_same_mesh_positive_matrix(
            spaces[3],
            floquets[3],
            curl_coefficient=mu,
            mass_coefficient=mass,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        bundle["p1_matrix"] = assemble_same_mesh_positive_matrix(
            spaces[1],
            floquets[1],
            curl_coefficient=mu,
            mass_coefficient=mass,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        bundle["p63_local_transfer"] = build_same_mesh_hcurl_transfer(6, 3)
        bundle["p31_local_transfer"] = build_same_mesh_hcurl_transfer(3, 1)
        bundle["p63_owner_transfer"] = build_same_mesh_hcurl_owner_transfer(
            spaces[6],
            floquets[6],
            spaces[3],
            floquets[3],
            local_transfer=bundle["p63_local_transfer"],
        )
        bundle["p31_owner_transfer"] = build_same_mesh_hcurl_owner_transfer(
            spaces[3],
            floquets[3],
            spaces[1],
            floquets[1],
            local_transfer=bundle["p31_local_transfer"],
        )
        bundle["lower_cycle"] = SameMeshHcurlPmg(
            bundle["p3_matrix"],
            bundle["p1_matrix"],
            bundle["p31_owner_transfer"],
            owns_owner_transfer=True,
        )
        p6_map = floquets[6].mpc.function_space.dofmap.index_map
        p6_block_size = int(floquets[6].mpc.function_space.dofmap.index_map_bs)
        p6_owned_storage = int(p6_map.size_local) * p6_block_size
        p6_slaves = np.asarray(floquets[6].mpc.slaves, dtype=np.int64)
        owned_slaves = p6_slaves[
            (p6_slaves >= 0) & (p6_slaves < p6_owned_storage)
        ]
        bundle["upper_cycle"] = SameMeshP6NestedVcycle(
            bundle["p6_shell"],
            bundle["lower_cycle"],
            bundle["p63_owner_transfer"],
            bundle["p3_matrix"],
            owned_slave_indices=owned_slaves,
            owns_lower_cycle=True,
            owns_p63_transfer=True,
            owns_p6_shell=True,
        )
        return bundle
    except Exception:
        if p6_diagonal is not None:
            p6_diagonal.destroy()
        if p6_action is not None:
            p6_action.destroy()
        destroy_p6_same_mesh_setup_bundle(bundle)
        raise


def audit_p6_same_mesh_setup(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return actual retained/setup facts without applying the cycles."""

    spaces = bundle["spaces"]
    floquets = bundle["floquets"]
    matrices = {
        "p3": _matrix_facts(bundle["p3_matrix"]),
        "p1": _matrix_facts(bundle["p1_matrix"]),
    }
    layouts = {str(degree): _space_layout(spaces[degree]) for degree in P6_SETUP_LEVELS}
    action = _p6_action_facts(bundle["p6_shell"])
    transfers = {
        "p63": _transfer_facts(
            bundle["p63_local_transfer"], bundle["p63_owner_transfer"]
        ),
        "p31": _transfer_facts(
            bundle["p31_local_transfer"], bundle["p31_owner_transfer"]
        ),
    }
    work = {
        "upper": _work_facts(bundle["upper_cycle"]),
        "lower": _work_facts(bundle["lower_cycle"]),
    }
    smoothers = {
        "upper": _smoother_facts(bundle["upper_cycle"].smoother),
        "lower": _smoother_facts(bundle["lower_cycle"].smoother),
    }
    factor = _factor_facts(bundle["lower_cycle"])
    return {
        "schema": P6_SETUP_SCHEMA,
        "profile": {
            "wavelength_nm": P6_SETUP_WAVELENGTH_NM,
            "mesh_target_size_nm": P6_SETUP_MESH_TARGET_NM,
            "levels": list(P6_SETUP_LEVELS),
            "pairs": [list(pair) for pair in P6_SETUP_PAIRS],
            "same_physical_mesh": True,
            "finalized_double_floquet_mpc_count": int(
                sum(floquet.mpc is not None for floquet in floquets.values())
            ),
        },
        "layouts": layouts,
        "matrices": matrices,
        "p6_action": action,
        "transfers": transfers,
        "work_vectors": work,
        "smoothers": smoothers,
        "p1_factor": factor,
        "retained_ledger": _retained_ledger(
            bundle, matrices, transfers, action, work, smoothers, factor
        ),
        "architecture": {
            "p6_matrix_free": True,
            "p6_global_aij": False,
            "p3_sparse_allowed": True,
            "p1_sparse_allowed": True,
            "global_dense_transfer": False,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "p6_factor": False,
            "outer_ksp_created": False,
            "restart_reserve": False,
            "physical_solve": False,
            "dtn": False,
            "recovery": False,
            "high_order_global_aij": False,
        },
        "ownership": {
            "upper_owns_lower_cycle": True,
            "upper_owns_p63_transfer": True,
            "upper_owns_p6_shell": True,
            "destroy_order": [
                "upper_cycle",
                "p3_p1_matrices",
                "python_fe_objects",
            ],
        },
    }


def destroy_p6_same_mesh_setup_bundle(bundle: dict[str, Any]) -> None:
    """Destroy a setup bundle once, in nested-cycle to FE-object order."""

    if not bundle:
        return
    upper = bundle.pop("upper_cycle", None)
    lower = bundle.pop("lower_cycle", None)
    p63_owner = bundle.pop("p63_owner_transfer", None)
    p31_owner = bundle.pop("p31_owner_transfer", None)
    shell = bundle.pop("p6_shell", None)
    if upper is not None:
        upper.destroy()
    else:
        if lower is not None:
            lower.destroy()
        if p63_owner is not None:
            p63_owner.destroy()
        if shell is not None:
            shell.destroy()
        if p31_owner is not None and lower is None:
            p31_owner.destroy()
    for name in ("p3_matrix", "p1_matrix"):
        matrix = bundle.pop(name, None)
        if matrix is not None:
            matrix.destroy()
    bundle.clear()


__all__ = (
    "P6_SETUP_LEVELS",
    "P6_SETUP_MESH_TARGET_NM",
    "P6_SETUP_PAIRS",
    "P6_SETUP_SCHEMA",
    "P6_SETUP_WAVELENGTH_NM",
    "audit_p6_same_mesh_setup",
    "build_p6_same_mesh_setup",
    "destroy_p6_same_mesh_setup_bundle",
    "validate_p6_setup_config",
)
