"""The narrow V16 same-mesh physical p-coarse core.

The physical p-cycle is a variable preconditioner: the p6 positive smoother
is borrowed from the reviewed setup, while the p3 correction is obtained with
the exact p3 physical action and a right-FGMRES restart-20 inner solve.  This
module owns only the ten dedicated p-cycle vectors (eight p6 and two p3);
the setup, transfers, smoothers, and physical actions remain caller-owned.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .fullspace_memory_first_krylov import (
    destroy_krylov_result,
    run_restart20_cycles,
)


PHYSICAL_PCOARSE_SCHEMA = "task038.same_mesh_physical_pcoarse.v1"
PHYSICAL_PCOARSE_LEVELS = (6, 3, 1)
PHYSICAL_PCOARSE_RESTART = 20
PHYSICAL_PCOARSE_DEDICATED_P6_VECTORS = 8
PHYSICAL_PCOARSE_DEDICATED_P3_VECTORS = 2
SMALL_PHYSICAL_PROBE_NAMES = (
    "random",
    "gradient",
    "curl",
    "checkerboard",
    "physical_component_derived",
    "r3_long_tail_derived",
)


def _matrix_layout(matrix: Any, name: str) -> tuple[int, int, int, int]:
    global_rows, global_columns = (int(value) for value in matrix.getSize())
    local_rows, local_columns = (int(value) for value in matrix.getLocalSize())
    if global_rows != global_columns or local_rows != local_columns:
        raise ValueError(f"{name} matrix must have a square local/global layout")
    return global_rows, local_rows, global_columns, local_columns


def _owned_slave_indices(setup: Mapping[str, Any], local_size: int) -> np.ndarray:
    floquet = setup["floquets"][6]
    mpc = getattr(floquet, "mpc", None)
    if mpc is None:
        raise ValueError("physical p-cycle requires the finalized p6 Floquet MPC")
    slaves = np.asarray(mpc.slaves, dtype=np.int64).reshape(-1)
    owned = slaves[(slaves >= 0) & (slaves < int(local_size))]
    if np.unique(owned).size != owned.size:
        raise ValueError("physical p-cycle p6 slave rows are duplicated")
    result = np.asarray(owned, dtype=np.int32).copy()
    result.flags.writeable = False
    return result


class SameMeshPhysicalPcoarseV1:
    """One V16 ``S6``/``P63``/``A3`` physical p-cycle.

    The supplied setup and actions are borrowed.  The cycle owns only its
    eight p6 and two p3 work vectors; every inner FGMRES call owns and destroys
    its restart workspace before returning.
    """

    def __init__(
        self,
        setup: Mapping[str, Any],
        p6_action: Any,
        p3_action: Any,
        *,
        inner_max_it: int = 20,
    ) -> None:
        inner_max_it = int(inner_max_it)
        if inner_max_it not in (20, 100):
            raise ValueError("production inner_max_it must be 20 or 100")
        required = (
            "p6_shell",
            "p3_matrix",
            "upper_cycle",
            "lower_cycle",
            "p63_owner_transfer",
        )
        missing = [name for name in required if name not in setup]
        if missing:
            raise ValueError(f"physical p-cycle setup is missing {missing}")
        if not callable(getattr(p6_action, "apply", None)):
            raise TypeError("p6 physical action must provide apply(source, target)")
        if not callable(getattr(p3_action, "apply", None)):
            raise TypeError("p3 physical action must provide apply(source, target)")
        p6_matrix = setup["p6_shell"].matrix
        p3_matrix = setup["p3_matrix"]
        p6_global, p6_local, _, _ = _matrix_layout(p6_matrix, "p6")
        p3_global, p3_local, _, _ = _matrix_layout(p3_matrix, "p3")
        smoother = getattr(setup["upper_cycle"], "smoother", None)
        if not callable(getattr(smoother, "apply_into", None)):
            raise TypeError("physical p-cycle requires the setup-owned p6 smoother")
        transfer = setup["p63_owner_transfer"]
        for operation in ("apply_adjoint_into", "apply_primal_into"):
            if not callable(getattr(transfer, operation, None)):
                raise TypeError(f"p63 owner transfer lacks {operation}")
        if not callable(getattr(setup["lower_cycle"], "apply", None)):
            raise TypeError("physical p-cycle requires the lower positive cycle")

        self.setup = setup
        self.p6_action = p6_action
        self.p3_action = p3_action
        self.p6_matrix = p6_matrix
        self.p3_matrix = p3_matrix
        self.p6_smoother = smoother
        self.p63_transfer = transfer
        self.lower_cycle = setup["lower_cycle"]
        self._inner_max_it = inner_max_it
        self._p6_rhs_layout = (p6_global, p6_local)
        self._p6_target_layout = (p6_global, p6_local)
        self._p3_rhs_layout = (p3_global, p3_local)
        self._p3_target_layout = (p3_global, p3_local)
        self._owned_slave_indices = _owned_slave_indices(setup, p6_local)
        self._work: list[PETSc.Vec] = []
        self._destroyed = False
        self.apply_count = 0
        self.physical_action_count = 0
        self.p63_adjoint_count = 0
        self.p63_primal_count = 0
        self.p6_smoother_count = 0
        self.inner_call_count = 0
        self.last_apply_facts: dict[str, Any] = {}
        self.last_inner_facts: dict[str, Any] = {}
        try:
            self._allocate_work()
            self.audit = MappingProxyType(
                {
                    "schema": PHYSICAL_PCOARSE_SCHEMA,
                    "levels": list(PHYSICAL_PCOARSE_LEVELS),
                    "operator": "A6=S6/P63/A3/P63^H physical split-volume+streaming-DtN",
                    "p6_action": "borrowed_exact_physical_action",
                    "p3_action": "borrowed_exact_physical_action",
                    "p6_smoother": "borrowed_setup_owned_frozen_positive_chebyshev_jacobi",
                    "lower_cycle": "borrowed_setup_owned_p3_to_p1_positive_cycle",
                    "inner_solver": "right_fgmres_restart20_zero_start",
                    "inner_max_it": self._inner_max_it,
                    "dedicated_p6_vector_count": PHYSICAL_PCOARSE_DEDICATED_P6_VECTORS,
                    "dedicated_p3_vector_count": PHYSICAL_PCOARSE_DEDICATED_P3_VECTORS,
                    "dedicated_vector_count": PHYSICAL_PCOARSE_DEDICATED_P6_VECTORS
                    + PHYSICAL_PCOARSE_DEDICATED_P3_VECTORS,
                    "borrowed_objects_not_destroyed": True,
                    "owns_inner_restart_workspace": True,
                    "retains_global_physical_aij": False,
                    "retains_dense_dtn": False,
                    "retains_physical_factor": False,
                    "formula": {
                        "pre": "u6=S6*r6; r6'=r6-A6*u6",
                        "coarse": "r3=P63^H*r6'; e3=A3^-1*r3; u6'=u6+P63*e3",
                        "post": "r6''=r6-A6*u6'; M^-1*r6=u6'+S6*r6''",
                    },
                    "destroy_order": [
                        "inner_restart_ksp_and_basis",
                        "dedicated_p3_vectors",
                        "dedicated_p6_vectors",
                        "borrowed_setup_objects_by_caller",
                    ],
                }
            )
        except Exception:
            self.destroy()
            raise

    def _allocate_work(self) -> None:
        def add(vector: PETSc.Vec) -> PETSc.Vec:
            self._work.append(vector)
            return vector

        self._p6_pre = add(self.p6_matrix.createVecRight())
        self._p6_action = add(self.p6_matrix.createVecLeft())
        self._p6_residual = add(self.p6_matrix.createVecLeft())
        self._p6_correction = add(self.p6_matrix.createVecRight())
        self._p6_solution = add(self.p6_matrix.createVecRight())
        self._p6_post_action = add(self.p6_matrix.createVecLeft())
        self._p6_post_residual = add(self.p6_matrix.createVecLeft())
        self._p6_post_correction = add(self.p6_matrix.createVecRight())
        self._p3_rhs = add(self.p3_matrix.createVecLeft())
        self._p3_correction = add(self.p3_matrix.createVecRight())

    @property
    def work_vectors(self) -> tuple[PETSc.Vec, ...]:
        return tuple(self._work)

    def _require_vector(
        self, vector: PETSc.Vec, layout: tuple[int, int], name: str
    ) -> None:
        if (int(vector.getSize()), int(vector.getLocalSize())) != layout:
            raise ValueError(f"{name} vector has an incompatible layout")

    def _zero_owned_slaves(self, vector: PETSc.Vec) -> None:
        if self._owned_slave_indices.size:
            vector.array[self._owned_slave_indices] = 0.0 + 0.0j

    def _owned_slave_max(self, vector: PETSc.Vec) -> float:
        local = (
            float(np.max(np.abs(vector.array[self._owned_slave_indices])))
            if self._owned_slave_indices.size
            else 0.0
        )
        return float(
            self.p6_matrix.getComm().tompi4py().allreduce(local, op=MPI.MAX)
        )

    def _apply_p3_action(self, source: PETSc.Vec) -> PETSc.Vec:
        target = self.p3_matrix.createVecLeft()
        try:
            self.p3_action.apply(source, target)
        except Exception:
            target.destroy()
            raise
        return target

    def _apply_lower_cycle(self, source: PETSc.Vec) -> PETSc.Vec:
        return self.lower_cycle.apply(source)

    def solve_inner(self, rhs: PETSc.Vec, *, max_it: int = 20) -> dict[str, Any]:
        """Run one fixed-count inner solve, or the bounded 10000-step reference."""

        if self._destroyed:
            raise RuntimeError("physical p-cycle has been destroyed")
        max_it = int(max_it)
        if max_it not in (20, 100, 10000):
            raise ValueError("inner max_it is fixed to 20, 100, or 10000")
        self._require_vector(rhs, self._p3_rhs_layout, "p3 inner residual")
        result = run_restart20_cycles(
            rhs,
            self._apply_p3_action,
            self._apply_lower_cycle,
            max_it=max_it,
            residual_limit=1.0e-6 if max_it == 10000 else 0.0,
            resource_sample=lambda: {"sampled": False},
            start_iteration=0,
            checkpoint_writer=None,
            first_checkpoint_iteration=None,
            checkpoint_interval=PHYSICAL_PCOARSE_RESTART,
            stop_on_true_residual=max_it == 10000,
            ksp_type="fgmres",
        )
        iterations = int(result["iterations"])
        if max_it in (20, 100) and iterations != max_it:
            destroy_krylov_result(result)
            raise RuntimeError(
                f"fixed inner solve stopped at {iterations}, expected {max_it}"
            )
        self.inner_call_count += 1
        self.last_inner_facts = {
            "max_it": max_it,
            "iterations": iterations,
            "ksp_type": str(result["settings"]["ksp_type"]),
            "restart": int(result["settings"]["restart"]),
            "residual_replacement": bool(result["settings"]["residual_replacement"]),
            "explicit_action_count": int(result["explicit_action_count"]),
            "pc_apply_count": int(result["pc_apply_count"]),
            "ksp_destroy_count": int(result["ksp_destroy_count"]),
            "final_true_residual": float(result["final_true_residual"]),
        }
        return result

    def apply_into(self, rhs: PETSc.Vec, target: PETSc.Vec) -> dict[str, Any]:
        """Apply the V16 physical p-cycle into a caller-owned p6 target."""

        if self._destroyed:
            raise RuntimeError("physical p-cycle has been destroyed")
        self._require_vector(rhs, self._p6_rhs_layout, "p6 physical residual")
        self._require_vector(target, self._p6_target_layout, "p6 physical target")
        self.p6_smoother.apply_into(rhs, self._p6_pre)
        self.p6_smoother_count += 1
        self.p6_action.apply(self._p6_pre, self._p6_action)
        self.physical_action_count += 1
        rhs.copy(self._p6_residual)
        self._p6_residual.axpy(-1.0, self._p6_action)

        self.p63_transfer.apply_adjoint_into(self._p6_residual, self._p3_rhs)
        self.p63_adjoint_count += 1
        inner = self.solve_inner(self._p3_rhs, max_it=self._inner_max_it)
        try:
            inner["final_solution"].copy(self._p3_correction)
        finally:
            destroy_krylov_result(inner)
        self.p63_transfer.apply_primal_into(
            self._p3_correction, self._p6_correction
        )
        self.p63_primal_count += 1
        self._zero_owned_slaves(self._p6_correction)
        self._p6_pre.copy(self._p6_solution)
        self._p6_solution.axpy(1.0, self._p6_correction)

        self.p6_action.apply(self._p6_solution, self._p6_post_action)
        self.physical_action_count += 1
        rhs.copy(self._p6_post_residual)
        self._p6_post_residual.axpy(-1.0, self._p6_post_action)
        self.p6_smoother.apply_into(self._p6_post_residual, self._p6_post_correction)
        self.p6_smoother_count += 1
        self._p6_solution.axpy(1.0, self._p6_post_correction)
        self._zero_owned_slaves(self._p6_solution)
        self._p6_solution.copy(target)

        output_norm = float(target.norm())
        owned_slave_max = self._owned_slave_max(target)
        output_finite = bool(np.isfinite(output_norm))
        if not output_finite or not np.isfinite(owned_slave_max):
            raise RuntimeError("physical p-cycle output is non-finite")
        if owned_slave_max != 0.0:
            raise RuntimeError("physical p-cycle output is not slave-zero")
        self.apply_count += 1
        facts = {
            "formula": "S6 -> A6 -> P63^H -> A3^-1 -> P63 -> A6 -> S6",
            "p6_smoother_count": 2,
            "p63_adjoint_count": 1,
            "p63_primal_count": 1,
            "physical_action_count": 2,
            "inner_max_it": self._inner_max_it,
            "inner_facts": dict(self.last_inner_facts),
            "output_finite": output_finite,
            "owned_slave_max": owned_slave_max,
            "apply_count": int(self.apply_count),
        }
        self.last_apply_facts = facts
        return facts

    def apply(self, rhs: PETSc.Vec) -> PETSc.Vec:
        target = self.p6_matrix.createVecRight()
        try:
            self.apply_into(rhs, target)
        except Exception:
            target.destroy()
            raise
        return target

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        for vector in self._work:
            vector.destroy()
        self._work = []
        self._owned_slave_indices = np.empty(0, dtype=np.int32)
        self.setup = None
        self.p6_action = None
        self.p3_action = None
        self.p6_matrix = None
        self.p3_matrix = None
        self.p6_smoother = None
        self.p63_transfer = None
        self.lower_cycle = None


def destroy_same_mesh_physical_pcoarse(
    pcoarse: SameMeshPhysicalPcoarseV1 | None,
) -> None:
    """Idempotently release one physical p-cycle's owned vectors."""

    if pcoarse is not None:
        pcoarse.destroy()


def _build_small_same_mesh_positive_setup(cfg: Any, comm: Any) -> dict[str, Any]:
    """Build the h50 p6/p3/p1 positive support for the focused Q1 fixture."""

    from dolfinx import fem

    from .fullspace_lor_native_hx_fixture import build_frozen_fullspace_primal_source
    from .fullspace_mpc_action import build_fullspace_mpc_form_action
    from .fullspace_same_mesh_hcurl_pmg_global import (
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
    from .fullspace_same_mesh_hcurl_pmg import build_same_mesh_hcurl_transfer
    from .fullspace_same_mesh_hcurl_pmg_setup import (
        SAME_MESH_JIT_OPTIONS,
        destroy_p6_same_mesh_setup_bundle,
    )

    levels = _build_same_mesh_levels(cfg, comm, (6, 3, 1))
    setup: dict[str, Any] = {
        "schema": "task038.same_mesh_physical_pcoarse.small-positive.v1",
        **levels,
    }
    p6_action = None
    p6_diagonal = None
    try:
        spaces = setup["spaces"]
        floquets = setup["floquets"]
        p6_form = same_mesh_positive_form(
            spaces[6], curl_coefficient=setup["mu"], mass_coefficient=setup["mass"]
        )
        p6_action = build_fullspace_mpc_form_action(
            p6_form,
            spaces[6],
            mpc=floquets[6].mpc,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        p6_diagonal = build_constrained_jacobi_diagonal(
            fem.form(p6_form, jit_options=dict(SAME_MESH_JIT_OPTIONS)),
            floquets[6].mpc,
        )
        setup["p6_shell"] = SameMeshP6MatrixFreeShell(p6_action, p6_diagonal)
        p6_action = None
        p6_diagonal = None
        setup["p3_matrix"] = assemble_same_mesh_positive_matrix(
            spaces[3],
            floquets[3],
            curl_coefficient=setup["mu"],
            mass_coefficient=setup["mass"],
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        setup["p1_matrix"] = assemble_same_mesh_positive_matrix(
            spaces[1],
            floquets[1],
            curl_coefficient=setup["mu"],
            mass_coefficient=setup["mass"],
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        setup["p63_local_transfer"] = build_same_mesh_hcurl_transfer(6, 3)
        setup["p31_local_transfer"] = build_same_mesh_hcurl_transfer(3, 1)
        setup["p63_owner_transfer"] = build_same_mesh_hcurl_owner_transfer(
            spaces[6], floquets[6], spaces[3], floquets[3],
            local_transfer=setup["p63_local_transfer"],
        )
        setup["p31_owner_transfer"] = build_same_mesh_hcurl_owner_transfer(
            spaces[3], floquets[3], spaces[1], floquets[1],
            local_transfer=setup["p31_local_transfer"],
        )
        lower_seed, _ = build_frozen_fullspace_primal_source(
            spaces[3], floquets[3], cfg, "random"
        )
        try:
            from .fullspace_same_mesh_hcurl_pmg_global import SameMeshHcurlPmg

            setup["lower_cycle"] = SameMeshHcurlPmg(
                setup["p3_matrix"],
                setup["p1_matrix"],
                setup["p31_owner_transfer"],
                smoother_power_seed=lower_seed,
                owns_owner_transfer=True,
            )
        finally:
            lower_seed.destroy()
        index_map = floquets[6].mpc.function_space.dofmap.index_map
        block_size = int(floquets[6].mpc.function_space.dofmap.index_map_bs)
        owned_storage = int(index_map.size_local) * block_size
        slaves = np.asarray(floquets[6].mpc.slaves, dtype=np.int64)
        owned_slaves = slaves[(slaves >= 0) & (slaves < owned_storage)]
        upper_seed, _ = build_frozen_fullspace_primal_source(
            spaces[6], floquets[6], cfg, "random"
        )
        try:
            setup["upper_cycle"] = SameMeshP6NestedVcycle(
                setup["p6_shell"],
                setup["lower_cycle"],
                setup["p63_owner_transfer"],
                setup["p3_matrix"],
                smoother_power_seed=upper_seed,
                owned_slave_indices=owned_slaves,
                owns_lower_cycle=True,
                owns_p63_transfer=True,
                owns_p6_shell=True,
            )
        finally:
            upper_seed.destroy()
        return setup
    except Exception:
        if p6_diagonal is not None:
            p6_diagonal.destroy()
        if p6_action is not None:
            p6_action.destroy()
        destroy_p6_same_mesh_setup_bundle(setup)
        raise


def build_small_same_mesh_physical_pcoarse_case(
    cfg: Any, comm: Any
) -> dict[str, Any]:
    """Build the Q1 h50 same-mesh p6/p3/p1 physical-p-cycle fixture.

    The first four probes use the reviewed analytic source builder.  The
    physical-component probe reuses the existing p6 physical-RHS route and
    P63^H.  The R3 tail remains explicit until a matching canonical packet
    authority is available; no PETSc-row source is invented.
    """

    if int(cfg.nedelec_degree) != 6 or float(cfg.mesh_target_size) != 50.0:
        raise ValueError("small physical p-cycle fixture is fixed at p6/h50")
    from .fullspace_dtn_action import build_dynamic_mode_inventory
    from .fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )

    setup = _build_small_same_mesh_positive_setup(cfg, comm)
    p6_action_bundle = None
    p3_action_bundle = None
    pcoarse = None
    try:
        mode_inventory = build_dynamic_mode_inventory(cfg)
        p6_action_bundle = build_same_mesh_physical_action(
            setup, cfg, 6, mode_inventory=mode_inventory
        )
        p3_action_bundle = build_same_mesh_physical_action(
            setup, cfg, 3, mode_inventory=mode_inventory
        )
        pcoarse = SameMeshPhysicalPcoarseV1(
            setup,
            p6_action_bundle["action"],
            p3_action_bundle["action"],
        )
        return {
            "schema": PHYSICAL_PCOARSE_SCHEMA,
            "cfg": cfg,
            "setup": setup,
            "p6_action": p6_action_bundle,
            "p3_action": p3_action_bundle,
            "pcoarse": pcoarse,
            "mode_inventory": mode_inventory,
            "probe_names": SMALL_PHYSICAL_PROBE_NAMES,
        }
    except Exception:
        destroy_same_mesh_physical_pcoarse(pcoarse)
        if p3_action_bundle is not None:
            destroy_same_mesh_physical_action(p3_action_bundle)
        if p6_action_bundle is not None:
            destroy_same_mesh_physical_action(p6_action_bundle)
        from .fullspace_same_mesh_hcurl_pmg_setup import (
            destroy_p6_same_mesh_setup_bundle,
        )

        destroy_p6_same_mesh_setup_bundle(setup)
        raise


def build_small_same_mesh_probe_source(
    case: Mapping[str, Any], name: str
) -> tuple[PETSc.Vec, dict[str, Any]]:
    """Return a legal h50 probe, or report the missing canonical authority."""

    if name not in SMALL_PHYSICAL_PROBE_NAMES:
        raise ValueError(f"unknown fixed physical probe {name!r}")
    if name in SMALL_PHYSICAL_PROBE_NAMES[:4]:
        from .fullspace_lor_native_hx_fixture import build_frozen_fullspace_primal_source

        setup = case["setup"]
        return build_frozen_fullspace_primal_source(
            setup["spaces"][3], setup["floquets"][3], case["cfg"], name
        )
    if name == "physical_component_derived":
        from .fullspace_same_mesh_hcurl_pmg_physical import build_physical_rhs

        high_rhs, rhs_facts = build_physical_rhs(case["p6_action"])
        coarse_rhs = case["setup"]["p3_matrix"].createVecLeft()
        try:
            case["setup"]["p63_owner_transfer"].apply_adjoint_into(
                high_rhs, coarse_rhs
            )
            return coarse_rhs, {
                "name": name,
                "formula": "physical_rhs_compose_then_p63_adjoint",
                "phase_application": "finalized_floquet_mpc_once",
                "dual_role": "full_fe_dual",
                "high_rhs_facts": dict(rhs_facts),
                "high_degree": 6,
                "coarse_degree": 3,
            }
        except Exception:
            coarse_rhs.destroy()
            raise
        finally:
            high_rhs.destroy()
    raise NotImplementedError(
        f"no existing h50 authority maps the derived probe {name!r}; "
        "R3 requires canonical full-FE dual packets with matching p6 "
        "shape/key/provenance; do not synthesize it from PETSc rows or rank order"
    )


def destroy_small_same_mesh_physical_pcoarse_case(case: dict[str, Any]) -> None:
    """Release p-cycle, physical actions, then the borrowed setup owner."""

    if not case:
        return
    destroy_same_mesh_physical_pcoarse(case.pop("pcoarse", None))
    from .fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    p3_action = case.pop("p3_action", None)
    p6_action = case.pop("p6_action", None)
    if p3_action is not None:
        destroy_same_mesh_physical_action(p3_action)
    if p6_action is not None:
        destroy_same_mesh_physical_action(p6_action)
    setup = case.pop("setup", None)
    if setup is not None:
        from .fullspace_same_mesh_hcurl_pmg_setup import (
            destroy_p6_same_mesh_setup_bundle,
        )

        destroy_p6_same_mesh_setup_bundle(setup)
    case.clear()


__all__ = (
    "PHYSICAL_PCOARSE_DEDICATED_P3_VECTORS",
    "PHYSICAL_PCOARSE_DEDICATED_P6_VECTORS",
    "PHYSICAL_PCOARSE_LEVELS",
    "PHYSICAL_PCOARSE_RESTART",
    "PHYSICAL_PCOARSE_SCHEMA",
    "SMALL_PHYSICAL_PROBE_NAMES",
    "SameMeshPhysicalPcoarseV1",
    "build_small_same_mesh_physical_pcoarse_case",
    "build_small_same_mesh_probe_source",
    "destroy_same_mesh_physical_pcoarse",
    "destroy_small_same_mesh_physical_pcoarse_case",
)
