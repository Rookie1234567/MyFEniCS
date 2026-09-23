"""Selective V20 retained p6/p4 route for the opt-in D2 profile.

This is an adapter over the target mesh/action/ledger APIs.  It does not copy
the historical V14 runner or create a second watchdog.  The p6 operator keeps
only retained local Schur data; p4 owns one exact assembly-time-condensed
AIJ/factor and the original BAL_H callback uses the existing p6/p4 transfer.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Callable, Mapping

import numpy as np
from petsc4py import PETSc

from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.p4_cell_condensed_inverse import (
    P4CellCondensedInverse,
    P4RefinementLedger,
    assemble_condensed_ports,
    petsc_csr_content_identity,
)
from src.solvers.p6_cell_condensed_action import (
    P6CellCondensedAction,
    P6RetainedBALHBridge,
    build_p6_cell_condensed_action_from_carrier,
)


def _support_groups(space: Any, carrier: Any) -> tuple[tuple[np.ndarray, ...], tuple[int, ...]]:
    """Map each current carrier entry to owned cells without dense FE support."""

    mesh = space.mesh
    owned_cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    dof_to_cells: dict[int, set[int]] = {}
    for cell in range(owned_cells):
        local = np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int32)
        global_ids = np.asarray(space.dofmap.index_map.local_to_global(local), dtype=np.int64)
        for row in global_ids:
            dof_to_cells.setdefault(int(row), set()).add(int(cell))

    groups: list[np.ndarray] = []
    group_by_row: list[int] = []
    known: dict[tuple[int, ...], int] = {}
    for entry in tuple(carrier.entries):
        cells: set[int] = set()
        for name in ("coupling_rows", "projection_rows"):
            for row in np.asarray(getattr(entry, name), dtype=np.int64).reshape(-1):
                cells.update(dof_to_cells.get(int(row), ()))
        key = tuple(sorted(cells))
        if not key:
            raise ValueError("a DtN carrier entry has no local FE support")
        group = known.get(key)
        if group is None:
            group = len(groups)
            known[key] = group
            groups.append(np.asarray(key, dtype=np.int64))
        group_by_row.append(group)
    return tuple(groups), tuple(group_by_row)


def _compile_volume_form(volume_action: Any) -> Any:
    from dolfinx import fem

    form = getattr(volume_action, "bilinear_form", None)
    if form is None:
        raise RuntimeError("target volume action does not expose its borrowed bilinear form")
    return fem.form(form)


def _failure_diagnostic_jsonable(value: Any) -> Any:
    """Serialize failure diagnostics without placing arrays/nonfinite floats in JSON."""

    if isinstance(value, Mapping):
        return {str(key): _failure_diagnostic_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_failure_diagnostic_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        finite = bool(np.isfinite(value).all()) if np.issubdtype(value.dtype, np.number) else False
        return {
            "array_omitted": True,
            "dtype": str(value.dtype),
            "shape": [int(item) for item in value.shape],
            "finite": finite,
        }
    if isinstance(value, (complex, np.complexfloating)):
        number = complex(value)
        return [float(number.real), float(number.imag)]
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if np.isfinite(number) else {"nonfinite": str(number)}
    if isinstance(value, np.generic):
        return _failure_diagnostic_jsonable(value.item())
    return value


def persist_p4_failure_packet(
    packet: Mapping[str, Any],
    directory: Any,
    *,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    append: Callable[[str, Mapping[str, Any]], None],
) -> dict[str, Any]:
    """Persist raw p4 failure vectors in NPZ and only scalar diagnostics in JSONL."""

    from pathlib import Path

    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    logical = int(packet.get("factor_counts", {}).get("logical_apply_calls", 0))
    path = root / f"p4_failure_{logical:04d}.npz"
    suffix = 1
    while path.exists():
        path = root / f"p4_failure_{logical:04d}_{suffix:02d}.npz"
        suffix += 1
    arrays: dict[str, np.ndarray] = {}
    array_facts: dict[str, dict[str, Any]] = {}
    for name in ("g", "c", "r", "port_state"):
        value = packet.get(name)
        if value is None:
            continue
        array = np.ascontiguousarray(np.asarray(value, dtype=np.complex128))
        arrays[name] = array
        array_facts[name] = {
            "dtype": str(array.dtype),
            "shape": [int(item) for item in array.shape],
            "finite": bool(np.isfinite(array).all()),
        }
    np.savez(path, **arrays)
    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    record = {
        "schema": "task039extra.v20.p4-failure-packet.v1",
        "status": "P4_NUMERICAL_UNQUALIFIED",
        "source_sha": str(source_sha),
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "matrix_identity": _failure_diagnostic_jsonable(packet.get("matrix_identity", {})),
        "factor_counts": _failure_diagnostic_jsonable(packet.get("factor_counts", {})),
        "rows": _failure_diagnostic_jsonable(packet.get("rows", [])),
        "array_artifact": {
            "filename": path.name,
            "sha256": file_sha256,
            "arrays": array_facts,
            "allow_nonfinite_values": True,
        },
    }
    append("p4_failure_packets.jsonl", record)
    return record


@dataclass
class RetainedCondensedRuntime:
    """Owned D2 component bundle; no parent/watchdog ownership is hidden here."""

    levels: dict[str, Any]
    fine: dict[str, Any]
    p4: dict[str, Any]
    p6_system: Any
    p6_action: P6CellCondensedAction
    p4_system: Any
    p4_terms: Mapping[int, Any]
    mode_count: int
    mode_sha256: str
    coarse_degree: int = 4
    sum_factorized_work: bool = False
    pc_physical: dict[str, Any] | None = None
    p4_factor: Any = None
    p4_inverse: P4CellCondensedInverse | None = None
    p4_ledger: P4RefinementLedger | None = None
    h6: Any = None
    transfer: Any = None
    bridge: P6RetainedBALHBridge | None = None
    bal_h: Any = None
    transfer_owner: Any = None
    postprocess_jit: dict[str, Any] | None = None
    solver_stack_released: bool = False
    destroyed: bool = False

    @classmethod
    def build(
        cls,
        cfg: Any,
        comm: Any,
        *,
        coarse_degree: int = 4,
        sum_factorized_work: bool = False,
        marker: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> "RetainedCondensedRuntime":
        from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            build_same_mesh_physical_action,
        )
        from src.solvers.fullspace_physical_intermediate_runtime import (
            fine_volume_quadrature_metadata,
        )
        from src.solvers.physical_equivalent_fast import (
            build_packed_physical_action,
        )

        if int(comm.size) != 1:
            raise ValueError("the D2 retained route is qualified for MPI1 only")
        coarse_degree = int(coarse_degree)
        notify = (lambda name, facts: marker(name, dict(facts))) if marker else (lambda *_: None)
        levels = _build_same_mesh_levels(
            cfg, comm, (6, coarse_degree), include_positive_coefficients=True
        )
        notify("retained_shared_mesh_complete", {"degrees": [6, coarse_degree]})
        volume_quadrature_metadata, quadrature_records = fine_volume_quadrature_metadata(
            levels, cfg
        )
        notify(
            "retained_volume_quadrature_metadata_complete",
            {"records": quadrature_records},
        )
        fine = build_same_mesh_physical_action(
            levels,
            cfg,
            6,
            volume_quadrature_metadata=volume_quadrature_metadata,
        )
        p4 = None
        pc_physical = None
        try:
            p4 = build_same_mesh_physical_action(
                levels,
                cfg,
                coarse_degree,
                mode_inventory=(fine["modes"], fine["mode_rows"], fine["mode_sha256"]),
                volume_quadrature_metadata=volume_quadrature_metadata,
            )
            if sum_factorized_work:
                pc_physical = build_packed_physical_action(
                    {"levels": levels, "fine": fine},
                    cfg,
                    contiguous_work=True,
                    preallocated_work=False,
                    sum_factorized_work=True,
                )
                notify(
                    "retained_sum_factorized_physical_action_complete",
                    pc_physical["facts"],
                )
            cell_tags = levels["mesh_data"].cell_tags
            p6_space = levels["spaces"][6]
            p4_space = levels["spaces"][coarse_degree]
            p6_carrier = fine["dtn_action"].carrier
            p4_carrier = p4["dtn_action"].carrier
            p6_form = _compile_volume_form(fine["volume_action"])
            p4_form = _compile_volume_form(p4["volume_action"])
            notify("retained_forms_compiled", {"p6": True, "p4": True})
            p6_system = build_unconstrained_assembly_time_condensation(
                p6_form,
                p6_space,
                cell_tags,
                mpc=levels["floquets"][6].mpc,
                appended_global_rows=len(p6_carrier.entries),
                materialize_global_matrix=False,
                retain_local_schur_for_matrix_free=True,
                sum_duplicate_cell_integrals=True,
                strict_local_checks=True,
                geometry_identity_policy="raw_unrounded",
                share_identity_cache=True,
            )
            p6_action = build_p6_cell_condensed_action_from_carrier(
                p6_system, p6_carrier, owns_condensed=True
            )
            groups, group_by_row = _support_groups(p4_space, p4_carrier)
            p4_system = build_unconstrained_assembly_time_condensation(
                p4_form,
                p4_space,
                cell_tags,
                mpc=levels["floquets"][coarse_degree].mpc,
                appended_global_rows=len(p4_carrier.entries),
                appended_support_owned_cell_groups=groups,
                appended_support_group_by_row=group_by_row,
                materialize_global_matrix=True,
                retain_local_schur_for_matrix_free=False,
                dense_appended_block=True,
                sum_duplicate_cell_integrals=True,
                strict_local_checks=True,
                defer_final_assembly=True,
                geometry_identity_policy="raw_unrounded",
                share_identity_cache=True,
            )
            p4_terms = assemble_condensed_ports(p4_system, p4_carrier)
            # Port H/B/D insertion occurs after trace Schur insertion; finish
            # the one retained AIJ only after its complete augmented pattern
            # is present.
            p4_system.matrix.assemble()
            notify(
                "retained_condensed_components_complete",
                {
                    "p6_build": p6_system.build_audit,
                    "p4_build": p4_system.build_audit,
                    "p4_matrix_identity": petsc_csr_content_identity(p4_system.matrix),
                    "coarse_degree": coarse_degree,
                    "mode_count": len(fine["modes"]),
                    "mode_sha256": fine["mode_sha256"],
                },
            )
            return cls(
                levels=levels,
                fine=fine,
                p4=p4,
                p6_system=p6_system,
                p6_action=p6_action,
                p4_system=p4_system,
                p4_terms=p4_terms,
                mode_count=len(fine["modes"]),
                mode_sha256=str(fine["mode_sha256"]),
                coarse_degree=coarse_degree,
                sum_factorized_work=bool(sum_factorized_work),
                pc_physical=pc_physical,
            )
        except BaseException:
            from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
                destroy_same_mesh_physical_action,
            )

            for value in locals().get("p6_action", None), locals().get("p6_system", None), locals().get("p4_system", None):
                if value is not None:
                    destroy = getattr(value, "destroy", None)
                    if callable(destroy):
                        destroy()
            failed_pc = locals().get("pc_physical")
            if failed_pc is not None:
                failed_action = failed_pc.get("physical_action")
                if failed_action is not None:
                    failed_action.destroy()
            destroy_same_mesh_physical_action(fine)
            destroy_same_mesh_physical_action(p4)
            levels.clear()
            raise

    def attach_p4_factor(
        self,
        *,
        sample: Callable[[], Mapping[str, Any]],
        marker: Callable[[str, Mapping[str, Any]], None],
        failure_sink: Callable[[dict[str, Any]], None] | None = None,
        future_bytes: int = 0,
    ) -> dict[str, Any]:
        """Run the existing symbolic/numeric lifecycle on the p4 matrix."""

        from src.solvers.fullspace_p4_reference import reference_budget
        from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

        matrix = self.p4_system.matrix
        if matrix is None:
            raise RuntimeError("p4 condensed matrix was not materialized")
        factor = _MumpsFactor(matrix)
        try:
            pre = sample()
            if pre.get("icntl23") == 0:
                factor.set_icntl(23, 0)
            marker("reference_symbolic_started", {"route": "retained_v20_p4"})
            factor.symbolic(matrix)
            symbolic = {
                "symbolic_calls": int(factor.symbolic_calls),
                "numeric_calls": int(factor.numeric_calls),
                "solve_calls": int(factor.solve_calls),
                "info": factor.info((1, 7, 16, 22, 29)),
                "icntl23": factor.get_icntl(23),
            }
            if pre.get("icntl23") == 0 and symbolic["icntl23"] != 0:
                raise RuntimeError("MUMPS ICNTL(23) readback was not zero")
            marker("reference_symbolic_complete", symbolic)
            budget = reference_budget(
                sample(), symbolic["info"], int(future_bytes), marker=marker
            )
            factor.numeric(matrix)
            numeric = {
                "symbolic_calls": int(factor.symbolic_calls),
                "numeric_calls": int(factor.numeric_calls),
                "solve_calls": int(factor.solve_calls),
                "info": factor.info((1, 7, 16, 22, 29)),
                "budget": budget,
            }
            marker("reference_numeric_complete", numeric)
            inverse = P4CellCondensedInverse(
                self.p4_system,
                factor,
                port_terms=self.p4_terms,
                owns_condensed=True,
                owns_factor=True,
                retain_through_postprocess_v18=False,
            )
            self.p4_factor = factor
            self.p4_inverse = inverse
            self.p4_ledger = P4RefinementLedger(
                inverse,
                self.apply_original_a4,
                port_closure=self.port_closure,
                failure_sink=failure_sink,
            )
            factor = None
            return {"symbolic": symbolic, "numeric": numeric}
        finally:
            if factor is not None:
                factor.destroy()

    def prepare_postprocess_jit(
        self,
        *,
        marker: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Compile the official recovery Form/Expression objects before p4.

        The production recovery functions remain the source of truth.  This
        only constructs their existing H(curl)->DG Expression and scalar
        diagnostic Forms against the same D3 mesh/function space, so their
        first-use JIT cannot occur after the retained factor is allocated.
        The Python holders are released immediately after this preparation;
        the disk JIT cache remains available to the official recovery path.
        """

        if self.postprocess_jit is not None:
            return dict(self.postprocess_jit["facts"])
        from dolfinx import fem
        import ufl

        cfg = self.fine["cfg"]
        setup = self.fine["setup"]
        mesh_data = setup["mesh_data"]
        floquet = setup["floquets"][6]
        field = fem.Function(floquet.mpc.function_space, name="retained_postprocess_jit_field")
        dg = fem.functionspace(mesh_data.mesh, ("DG", int(cfg.visualization_degree), (3,)))
        points = dg.element.interpolation_points
        points = points() if callable(points) else points
        curl = ufl.curl(field)
        expressions = {
            "save_airbox_H_from_curl": fem.Expression(
                (cfg.magnetic_field_scale_A_per_m / (1j * cfg.k0 * cfg.mu_r)) * curl,
                points,
            ),
            "diffraction_H_from_curl": fem.Expression(
                (1.0 / (1j * cfg.k0 * cfg.mu_r)) * curl,
                points,
            ),
        }
        dx = ufl.Measure("dx", domain=mesh_data.mesh, subdomain_data=mesh_data.cell_tags)
        physical_dx = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))
        forms: dict[str, Any] = {}
        for component in range(3):
            forms[f"field_component_l2_{component}"] = fem.form(
                ufl.inner(field[component], field[component]) * physical_dx
            )
        for name, tag, epsilon in (
            ("grating", cfg.tags.grating, cfg.eps_grating),
            ("substrate", cfg.tags.substrate, cfg.eps_substrate),
        ):
            forms[f"region_volume_{name}"] = fem.form(ufl.as_ufl(1.0) * dx(tag))
            density_scale = 0.5 * cfg.k0 * float(complex(epsilon).imag)
            forms[f"volume_absorption_{name}"] = fem.form(
                density_scale * ufl.real(ufl.inner(field, field)) * dx(tag)
            )
        facts = {
            "status": "POSTPROCESS_JIT_PREFACTOR_PASS",
            "same_mesh_identity": "fine.setup.mesh_data.mesh",
            "function_space": "fine.setup.floquets[6].mpc.function_space",
            "expression_roles": sorted(expressions),
            "form_roles": sorted(forms),
            "expression_count": len(expressions),
            "form_count": len(forms),
            "official_consumers": [
                "save_airbox_3d_fields",
                "compute_diffraction_orders_3d",
                "_field_component_l2_metrics",
                "compute_volume_absorption_3d",
            ],
            "compiled_before_p4_factor": True,
        }
        self.postprocess_jit = {
            "field": field,
            "dg": dg,
            "expressions": expressions,
            "forms": forms,
            "facts": facts,
        }
        if marker is not None:
            marker("retained_postprocess_jit_complete", facts)
        return dict(facts)

    def release_postprocess_jit(
        self,
        *,
        marker: Callable[[str, Mapping[str, Any]], None] | None = None,
        after_recovery: bool = False,
    ) -> dict[str, Any]:
        """Release precompiled postprocessing holders after recovery/checks."""

        if self.postprocess_jit is None:
            return {"status": "ALREADY_RELEASED"}
        import gc

        facts = dict(self.postprocess_jit["facts"])
        expressions = self.postprocess_jit.pop("expressions", {})
        forms = self.postprocess_jit.pop("forms", {})
        self.postprocess_jit.pop("field", None)
        self.postprocess_jit.pop("dg", None)
        self.postprocess_jit.clear()
        self.postprocess_jit = None
        del expressions, forms
        gc.collect()
        facts.update(
            {
                "status": "POSTPROCESS_JIT_RELEASED",
                "release_context": "after_recovery" if after_recovery else "cleanup",
            }
        )
        if after_recovery:
            facts["released_after_recovery"] = True
        if marker is not None:
            marker("retained_postprocess_jit_released", facts)
        return facts

    def port_closure(
        self,
        solution: PETSc.Vec,
        port_state: np.ndarray,
    ) -> Mapping[str, Any]:
        """Evaluate the original carrier port rows ``H*a-D*c``.

        This is deliberately separate from the original FE ``A4`` action:
        carrier projection rows are read once from the caller-owned solution,
        while the accumulated port state is supplied by the refinement ledger.
        """

        entries = tuple(self.p4["dtn_action"].carrier.entries)
        alpha = np.ascontiguousarray(port_state, dtype=np.complex128).reshape(-1)
        if alpha.shape != (len(entries),) or not np.isfinite(alpha).all():
            raise ValueError("p4 port state has the wrong shape or is non-finite")
        net = np.zeros(len(entries), dtype=np.complex128)
        h_term = np.zeros_like(net)
        d_term = np.zeros_like(net)
        for port, entry in enumerate(entries):
            rows = np.asarray(entry.projection_rows, dtype=PETSc.IntType)
            values = np.asarray(entry.projection_values, dtype=np.complex128)
            if rows.shape != values.shape:
                raise ValueError("p4 carrier projection rows and values differ")
            c_values = np.asarray(solution.getValues(rows), dtype=np.complex128)
            h_term[port] = complex(entry.normalization_h) * alpha[port]
            d_term[port] = np.dot(values, c_values)
        net[:] = h_term - d_term
        norm = float(np.linalg.norm(net))
        scale = float(np.linalg.norm(h_term) + np.linalg.norm(d_term))
        relative = (
            0.0
            if scale == 0.0 and norm == 0.0
            else np.inf
            if scale == 0.0
            else norm / scale
        )
        finite = bool(
            np.isfinite(net).all()
            and np.isfinite(h_term).all()
            and np.isfinite(d_term).all()
            and np.isfinite(relative)
        )
        return {
            "status": "PASS"
            if finite and relative <= 1.0e-10
            else "P4_NUMERICAL_UNQUALIFIED",
            "finite": finite,
            "norm": norm,
            "scale": scale,
            "relative_residual": float(relative),
            "tolerance": 1.0e-10,
            "size": int(net.size),
            "h_term_norm": float(np.linalg.norm(h_term)),
            "d_term_norm": float(np.linalg.norm(d_term)),
            "sha256": hashlib.sha256(net.tobytes()).hexdigest(),
            "formula": "H*a-D*c",
            "rhs_policy": "zero_port_rhs",
        }

    def apply_original_a4(self, solution: PETSc.Vec, port_state: np.ndarray) -> PETSc.Vec:
        """Apply the independent original A4 action into owned storage.

        ``port_state`` is audited by the ledger separately; it must not be
        folded into a volume-only ``V*c+B*a`` approximation here.
        """

        if solution.getSize() != self.p4_system.full_rows:
            raise ValueError("p4 original action received the wrong FE vector")
        if port_state.shape != (self.p4_system.appended_rows,):
            raise ValueError("p4 original action received the wrong port state")
        from src.solvers.fullspace_physical_intermediate import apply_owned

        output = solution.duplicate()
        try:
            apply_owned(self.p4["physical_action"], solution, output)
            return output
        except BaseException:
            output.destroy()
            raise

    def build_bal_h(
        self,
        *,
        marker: Callable[[str, Mapping[str, Any]], None],
        audit_append: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> P6RetainedBALHBridge:
        """Attach existing H6, p6->p4 transfer, and exact p4 coarse inverse."""

        if self.p4_ledger is None or self.p4_inverse is None:
            raise RuntimeError("p4 symbolic/numeric must complete before BAL_H")
        from src.solvers.fullspace_same_mesh_hcurl_pmg_runtime import (
            build_same_mesh_hcurl_owner_transfer,
        )
        from src.solvers.fullspace_physical_intermediate_runtime import (
            AlgebraicOwnerTransfer,
        )
        from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling
        from src.solvers.physical_light_setup import build_light_h6_setup
        from dolfinx.la.petsc import create_vector

        positive = build_light_h6_setup(
            self.levels,
            self.fine["cfg"],
            marker,
            packed_power10=self.sum_factorized_work,
            packed_apply=True,
            sum_factorized_work=self.sum_factorized_work,
            sum_factorized_power10=self.sum_factorized_work,
        )
        # Transfer construction can fail after H6 setup.  Make its existing
        # owner visible to runtime.destroy as soon as it is created.
        self.h6 = positive
        transfer_owner = build_same_mesh_hcurl_owner_transfer(
            self.levels["spaces"][6],
            self.levels["floquets"][6],
            self.levels["spaces"][self.coarse_degree],
            self.levels["floquets"][self.coarse_degree],
            fixed_serial_owner_route=self.sum_factorized_work,
            optimized_owner_apply=self.sum_factorized_work,
        )
        self.transfer_owner = transfer_owner
        transfer = AlgebraicOwnerTransfer(transfer_owner)
        self.transfer = transfer

        def coarse(source: PETSc.Vec) -> PETSc.Vec:
            rhs = transfer.apply_adjoint(source)
            value = None
            logical_before = self.p4_ledger.logical_apply_calls
            try:
                value = self.p4_ledger.solve(rhs)
                audit = dict(self.p4_ledger.last_audit)
                audit.update(
                    {
                        "logical_apply": int(self.p4_ledger.logical_apply_calls),
                        "logical_apply_delta": int(
                            self.p4_ledger.logical_apply_calls - logical_before
                        ),
                        "source": "retained_bal_h_coarse",
                    }
                )
                if audit_append is not None:
                    audit_append("p4_decisions.jsonl", audit)
                result = transfer.apply_primal(value)
                return result
            finally:
                if value is not None:
                    value.destroy()
                rhs.destroy()

        def smoother(source: PETSc.Vec) -> PETSc.Vec:
            return positive["h6"].apply(source)

        def physical(source: PETSc.Vec) -> PETSc.Vec:
            from src.solvers.fullspace_physical_intermediate import apply_owned

            action = (
                self.pc_physical["physical_action"]
                if self.pc_physical is not None
                else self.fine["physical_action"]
            )
            return apply_owned(action, source)

        coupling = PhysicalBalancedCoupling(
            physical,
            coarse,
            smoother,
            transfer.apply_adjoint,
            route="BAL_H",
            checkpoint=lambda: None,
        )
        self.bal_h = coupling

        def bal_h_numpy(source: np.ndarray) -> np.ndarray:
            values = np.ascontiguousarray(source, dtype=np.complex128).reshape(-1)
            space = self.levels["spaces"][6]
            vector = create_vector(
                [(space.dofmap.index_map, int(space.dofmap.index_map_bs))]
            )
            output = None
            try:
                if vector.getSize() != values.size:
                    raise ValueError("BAL_H bridge source has the wrong FE size")
                vector.array[:] = values
                output = self.bal_h.apply(vector)
                result = np.asarray(
                    output.getArray(readonly=True), dtype=np.complex128
                ).copy()
                if result.shape != values.shape or not np.isfinite(result).all():
                    raise FloatingPointError("BAL_H bridge returned an invalid FE vector")
                return result
            finally:
                if output is not None:
                    output.destroy()
                vector.destroy()

        self.bridge = P6RetainedBALHBridge(self.p6_action, bal_h_numpy)
        marker("retained_bal_h_bridge_complete", {"route": "BAL_H"})
        return self.bridge


    def _clear_solver_stack(self) -> dict[str, Any]:
        """Destroy retained solver owners without asserting a recovery gate."""

        if self.solver_stack_released:
            return {
                "status": "ALREADY_RELEASED",
                "fine_action_alive": self.fine is not None and not self.destroyed,
            }

        if self.p4_inverse is not None:
            self.p4_inverse.destroy()
            self.p4_inverse = None
            self.p4_factor = None
            self.p4_system = None
            self.p4_ledger = None
        elif self.p4_system is not None:
            destroy = getattr(self.p4_system, "destroy", None)
            if callable(destroy):
                destroy()
            self.p4_system = None
            self.p4_factor = None
            self.p4_ledger = None

        if self.p6_action is not None:
            self.p6_action.destroy()
            self.p6_action = None
        self.p6_system = None

        if self.h6 is not None:
            for key in ("h6", "p6_shell"):
                value = self.h6.pop(key, None)
                destroy = getattr(value, "destroy", None)
                if callable(destroy):
                    destroy()
            self.h6 = None
        if self.transfer_owner is not None:
            self.transfer_owner.destroy()
            self.transfer_owner = None

        self.p4_terms = {}
        self.bridge = None
        self.bal_h = None
        self.transfer = None
        if self.pc_physical is not None:
            action = self.pc_physical.get("physical_action")
            if action is not None:
                action.destroy()
            self.pc_physical = None
        self.solver_stack_released = True
        return {
            "status": "CLEARED",
            "factor_released_before_matrix": True,
            "p6_retained_cache_released": True,
            "owner_refs_cleared": True,
            "fine_action_alive": self.fine is not None and not self.destroyed,
        }

    def release_solver_stack(
        self,
        *,
        field_saved: bool,
        pre_release_a6_checked: bool,
        marker: Callable[[str, Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Release solver owners only after the real field/A6 boundary."""

        if self.solver_stack_released:
            return {"status": "ALREADY_RELEASED", "fine_action_alive": not self.destroyed}
        if not field_saved or not pre_release_a6_checked:
            raise RuntimeError(
                "retained solver release requires saved field and pre-release A6 check"
            )
        if marker is not None:
            marker(
                "retained_solver_stack_release_started",
                {
                    "field_saved": True,
                    "pre_release_A6_checked": True,
                    "factor_before_matrix": True,
                },
            )
        cleanup = self._clear_solver_stack()
        facts = {
            **cleanup,
            "status": "RELEASED",
            "field_saved": True,
            "pre_release_A6_checked": True,
        }
        if marker is not None:
            marker("retained_solver_stack_release_complete", facts)
        return facts

    def destroy(self) -> None:
        if self.destroyed:
            return
        if not self.solver_stack_released:
            # Exception cleanup must not fabricate saved-field/A6 facts.
            self._clear_solver_stack()
        if self.postprocess_jit is not None:
            self.release_postprocess_jit()
        self.destroyed = True
        from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
            destroy_same_mesh_physical_action,
        )

        destroy_same_mesh_physical_action(self.fine)
        destroy_same_mesh_physical_action(self.p4)
        if self.pc_physical is not None:
            action = self.pc_physical.get("physical_action")
            if action is not None:
                action.destroy()
            self.pc_physical = None
        self.levels.clear()
        self.p4_terms = {}
        self.bridge = None
        self.bal_h = None
        self.transfer = None
        self.p4_factor = None


def _native_aq_projection_check(runtime: RetainedCondensedRuntime) -> dict[str, Any]:
    """Compare the independent native Aq split with Pq^H A6 Pq on this runtime.

    This is the V5 setup identity from the frozen V14 common builder, adapted
    to the retained runtime's already-owned q/p6 actions and algebraic owner
    transfer.  Volume and DtN are compared separately so neither component can
    hide a mismatch in the other.
    """

    from dolfinx.la.petsc import create_vector
    from src.solvers.fullspace_physical_intermediate import (
        BorrowedActionAdapter,
        apply_owned,
    )

    q_space = runtime.levels["spaces"][runtime.coarse_degree]
    transfer = runtime.transfer
    if transfer is None:
        raise RuntimeError("Aq projection requires the retained algebraic owner transfer")
    primal_before = int(transfer.primal_count)
    adjoint_before = int(transfer.adjoint_count)

    q = create_vector([(q_space.dofmap.index_map, q_space.dofmap.index_map_bs)])
    owned: list[Any] = [q]

    def own_apply(action: Any, source: Any, *, borrowed: bool = False) -> Any:
        adapter = BorrowedActionAdapter(action) if borrowed else action
        value = apply_owned(adapter, source)
        owned.append(value)
        return value

    def relative(left: Any, right: Any) -> dict[str, float]:
        difference = left.duplicate()
        try:
            left.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), right)
            absolute = float(difference.norm())
            denominator = max(float(left.norm()), np.finfo(float).tiny)
            ratio = absolute / denominator
            if not np.isfinite(ratio):
                raise FloatingPointError("nonfinite native/projected Aq component identity")
            return {"absolute": absolute, "relative": ratio}
        finally:
            difference.destroy()

    try:
        indices = np.arange(q.array.size, dtype=np.float64)
        q.array[:] = np.sin(0.071 * (indices + 1.0)) + 1j * 0.37 * np.cos(
            0.113 * (indices + 1.0)
        )
        q.array[transfer.coarse_slaves] = 0.0
        q.ghostUpdate(
            addv=PETSc.InsertMode.INSERT_VALUES,
            mode=PETSc.ScatterMode.FORWARD,
        )
        q_input = np.asarray(q.array, dtype=np.complex128).copy()
        q_norm = float(q.norm())
        if not np.isfinite(q_norm) or q_norm <= np.finfo(float).tiny:
            raise FloatingPointError("nonzero coarse Aq probe collapsed to zero")

        p6 = transfer.apply_primal(q)
        owned.append(p6)
        p6_norm = float(p6.norm())
        if not np.isfinite(p6_norm) or p6_norm <= np.finfo(float).tiny:
            raise FloatingPointError("Pq projection of the Aq probe collapsed to zero")

        native_volume = own_apply(runtime.p4["volume_action"], q, borrowed=True)
        projected_volume_source = own_apply(
            runtime.fine["volume_action"], p6, borrowed=True
        )
        native_dtn = own_apply(runtime.p4["dtn_action"], q)
        projected_dtn_source = own_apply(runtime.fine["dtn_action"], p6)

        volume_slave_values = np.asarray(projected_volume_source.array)[
            transfer.fine_slaves
        ].copy()
        dtn_slave_values = np.asarray(projected_dtn_source.array)[
            transfer.fine_slaves
        ].copy()
        volume_slave_zero = bool(np.all(volume_slave_values == 0.0))
        dtn_slave_zero = bool(np.all(dtn_slave_values == 0.0))

        projected_volume = transfer.apply_adjoint(projected_volume_source)
        owned.append(projected_volume)
        projected_dtn = transfer.apply_adjoint(projected_dtn_source)
        owned.append(projected_dtn)

        volume_facts = relative(native_volume, projected_volume)
        dtn_facts = relative(native_dtn, projected_dtn)

        native_total = native_volume.duplicate()
        owned.append(native_total)
        native_volume.copy(native_total)
        native_total.axpy(PETSc.ScalarType(1.0), native_dtn)
        projected_total = projected_volume.duplicate()
        owned.append(projected_total)
        projected_volume.copy(projected_total)
        projected_total.axpy(PETSc.ScalarType(1.0), projected_dtn)
        total_facts = relative(native_total, projected_total)
        input_unchanged = bool(np.array_equal(q_input, np.asarray(q.array)))
        input_slave_zero = bool(np.all(q_input[transfer.coarse_slaves] == 0.0))
        limit = 1.0e-10
        passed = bool(
            input_slave_zero
            and input_unchanged
            and volume_slave_zero
            and dtn_slave_zero
            and volume_facts["relative"] <= limit
            and dtn_facts["relative"] <= limit
        )
        space_identity = {
            "coarse_global_rows": int(
                q_space.dofmap.index_map.size_global
                * q_space.dofmap.index_map_bs
            ),
            "fine_global_rows": int(
                runtime.levels["spaces"][6].dofmap.index_map.size_global
                * runtime.levels["spaces"][6].dofmap.index_map_bs
            ),
            "coarse_mode_sha256": str(runtime.p4["mode_sha256"]),
            "fine_mode_sha256": str(runtime.fine["mode_sha256"]),
        }
        return {
            "schema": "task039extra.v5.native-aq-projection-check.v1",
            "source_contract": "4bf2bba56cc2e568d56ff3096aeb4a108744f28d:_build_common.native_aq_projection_check",
            "probe": "deterministic_nonzero_coarse_vector_with_zero_MPC_slaves",
            "coarse_degree": int(runtime.coarse_degree),
            "space_identity": space_identity,
            "input_sha256": hashlib.sha256(q_input.tobytes()).hexdigest(),
            "input_unchanged": input_unchanged,
            "input_slave_zero": input_slave_zero,
            "q_norm": q_norm,
            "p6_norm": p6_norm,
            "native_Aq_volume_vs_PqH_A6_volume_P": volume_facts,
            "native_Aq_DtN_vs_PqH_A6_DtN_P": dtn_facts,
            "native_Aq_total_vs_PqH_A6_total_P": total_facts,
            "projected_A6_slave_rows_zero": {
                "volume": volume_slave_zero,
                "dtn": dtn_slave_zero,
                "volume_max_abs": float(np.max(np.abs(volume_slave_values)))
                if volume_slave_values.size
                else 0.0,
                "dtn_max_abs": float(np.max(np.abs(dtn_slave_values)))
                if dtn_slave_values.size
                else 0.0,
            },
            "limit": limit,
            "total_identity_policy": "record_only; native volume and DtN components gate independently",
            "passed": passed,
            "calls": {
                "native_Aq_volume": 1,
                "projected_A6_volume": 1,
                "native_Aq_DtN": 1,
                "projected_A6_DtN": 1,
                "transfer_primal_delta": int(transfer.primal_count - primal_before),
                "transfer_adjoint_delta": int(transfer.adjoint_count - adjoint_before),
            },
        }
    finally:
        for value in reversed(owned):
            value.destroy()


def run_retained_condensed_workflow(
    payload: Mapping[str, Any],
    directory: Any,
    *,
    source_sha: str,
    cfg: Any,
    contract: Mapping[str, Any],
    ledger: Any,
    sample: Callable[[], Mapping[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    """Run the opt-in retained V20 route through the existing worker contract.

    The function owns only the retained numerical objects.  The enclosing
    Task38 launcher/watchdog remains the sole parent/resource supervisor.
    """

    from pathlib import Path
    import json
    import time

    from dolfinx.la.petsc import create_vector
    from mpi4py import MPI
    from src.runners.physical_intermediate import _atomic_json
    from src.runners.physical_balanced_output import (
        compare_retained_5nm_output,
        compare_retained_v5_output,
    )
    from src.solvers.fullspace_memory_first_krylov import write_solution_checkpoint
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs,
        recover_p0_outputs,
    )

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    runtime: RetainedCondensedRuntime | None = None
    full_rhs = None
    reduced_rhs = None
    result = None
    saved_field = None
    release_facts = None
    checkpoints = directory / "retained_checkpoint_manifests"
    checkpoints.mkdir(exist_ok=True)
    full_checkpoints = directory / "full_solution_checkpoint_manifests"
    full_checkpoints.mkdir(exist_ok=True)
    recovery_packets = directory / "retained_recovery_packets"
    recovery_packets.mkdir(exist_ok=True)
    last_checkpoint = {-1}
    last_evaluation: dict[str, Any] = {"facts": None}

    def _storage_vector(values: np.ndarray):
        space = runtime.fine["setup"]["spaces"][6]
        vector = create_vector(
            [(space.dofmap.index_map, int(space.dofmap.index_map_bs))]
        )
        values = np.asarray(values, dtype=np.complex128).reshape(-1)
        if vector.getSize() != values.size:
            vector.destroy()
            raise ValueError("retained storage vector has the wrong global size")
        vector.array[:] = values
        vector.assemble()
        return vector

    def _a6_fact(field):
        applied = apply_owned(runtime.fine["physical_action"], field)
        residual = full_rhs.duplicate()
        try:
            full_rhs.copy(residual)
            residual.axpy(PETSc.ScalarType(-1.0), applied)
            rhs_norm = float(full_rhs.norm())
            absolute = float(residual.norm())
            relative = absolute / max(rhs_norm, np.finfo(float).tiny)
            return {
                "relative": relative,
                "absolute": absolute,
                "rhs_norm": rhs_norm,
                "finite": bool(np.isfinite(relative)),
            }
        finally:
            residual.destroy()
            applied.destroy()

    def _native_apply(values: np.ndarray) -> np.ndarray:
        vector = _storage_vector(values)
        output = None
        try:
            output = apply_owned(runtime.fine["physical_action"], vector)
            return np.asarray(
                output.getArray(readonly=True), dtype=np.complex128
            ).copy()
        finally:
            if output is not None:
                output.destroy()
            vector.destroy()

    def _mapped_native_residual_facts(raw_facts: Mapping[str, Any]) -> dict[str, float]:
        """Map the native evaluator schema to the runner/checker schema."""

        return {
            "original_A6_relative": float(raw_facts["native_residual_relative"]),
            "port_closure_relative": float(raw_facts["port_residual_relative"]),
            "internal_residual_relative": float(raw_facts["internal_residual_relative"]),
            "native_identity_relative": float(raw_facts["native_identity_relative"]),
            "schur_port_identity_relative": float(
                raw_facts["schur_port_identity_relative"]
            ),
        }

    try:
        from src.io.native_capacity_profile import V5_NATIVE_PROFILES

        profile_identity = str(payload["solver"]["preconditioner"])
        sum_factorized_work = profile_identity in V5_NATIVE_PROFILES
        route = "V20_V5_4BF2_SUM_FACTORIZED" if sum_factorized_work else "V20"
        ledger.marker("retained_runtime_build_started", {"route": route})
        coarse_degree = int(payload["solver"].get("coarse_degree", 4))
        runtime = RetainedCondensedRuntime.build(
            cfg,
            MPI.COMM_WORLD,
            coarse_degree=coarse_degree,
            sum_factorized_work=sum_factorized_work,
            marker=ledger.marker,
        )
        provenance = payload["provenance"]
        if profile_identity in V5_NATIVE_PROFILES:
            summary["provenance"] = {
                "input_sha256": provenance["input_sha256"],
                "physical_model_sha256": provenance["physical_model_sha256"],
            }
        cache_before = {
            "cache_identity": dict(runtime.p6_action.cache_identity),
            "buffer_inventory": dict(runtime.p6_action.buffer_inventory),
        }
        postprocess_jit_facts = runtime.prepare_postprocess_jit(marker=ledger.marker)
        postprocess_jit_release = runtime.release_postprocess_jit(marker=ledger.marker)
        ledger.marker(
            "retained_runtime_build_complete",
            {
                "mode_count": runtime.mode_count,
                "mode_sha256": runtime.mode_sha256,
                "coarse_degree": runtime.coarse_degree,
                "route": route,
                "postprocess_jit_prefactor": postprocess_jit_facts,
                "postprocess_jit_release_before_factor": postprocess_jit_release,
            },
        )
        p4_facts = runtime.attach_p4_factor(
            sample=sample,
            marker=ledger.marker,
            failure_sink=lambda packet: persist_p4_failure_packet(
                packet,
                directory / "p4_failure_packets",
                source_sha=source_sha,
                input_sha256=provenance["input_sha256"],
                physical_model_sha256=provenance["physical_model_sha256"],
                append=ledger.append,
            ),
        )
        summary["retained_runtime"] = {
            "route": route,
            "mode_count": runtime.mode_count,
            "mode_sha256": runtime.mode_sha256,
            "p6_operator_recipe": dict(runtime.p6_action.operator_recipe),
            "p6_cache_identity": dict(runtime.p6_action.cache_identity),
            "p6_buffer_inventory": dict(runtime.p6_action.buffer_inventory),
            "p4_build": dict(runtime.p4_system.build_audit),
            "p4_factor": p4_facts,
            "p4_inverse_retain_through_postprocess_v18": False,
            "postprocess_jit_prefactor": postprocess_jit_facts,
            "postprocess_jit_release_before_factor": postprocess_jit_release,
            "p6_cache_before_setup": cache_before,
        }
        if sum_factorized_work:
            coarse_space = runtime.levels["spaces"][runtime.coarse_degree]
            fine_space = runtime.levels["spaces"][6]
            summary["retained_runtime"]["space_identity"] = {
                "coarse_global_rows": int(
                    coarse_space.dofmap.index_map.size_global
                    * coarse_space.dofmap.index_map_bs
                ),
                "fine_global_rows": int(
                    fine_space.dofmap.index_map.size_global
                    * fine_space.dofmap.index_map_bs
                ),
                "coarse_mode_sha256": str(runtime.p4["mode_sha256"]),
                "fine_mode_sha256": str(runtime.fine["mode_sha256"]),
            }
        ledger.marker("retained_p4_factor_complete", p4_facts)
        bridge = runtime.build_bal_h(
            marker=ledger.marker, audit_append=ledger.append
        )
        summary["retained_runtime"]["bal_h"] = {
            "bridge": "P6RetainedBALHBridge",
            "outer_pc_logical_p4_contract": 2,
            "physical_matsolve_refinements": "ledger-recorded; up to 2 refinements per logical solve",
        }
        aq_projection_check = None
        if sum_factorized_work:
            aq_projection_check = _native_aq_projection_check(runtime)
            summary["retained_runtime"]["native_aq_projection_check"] = (
                aq_projection_check
            )
            ledger.marker(
                "retained_native_aq_projection_check_complete",
                aq_projection_check,
            )
            if not aq_projection_check["passed"]:
                raise RuntimeError(
                    "native Aq versus projected p6 operator identity failed: "
                    f"{aq_projection_check}"
                )

        full_rhs, rhs_facts = build_physical_rhs(runtime.fine)
        reduced_values = runtime.p6_action.reduce_rhs(
            full_rhs, rhs_is_mpc_dual=True
        )
        reduced_rhs = runtime.p6_action.create_reduced_rhs_vector()
        if reduced_rhs.getLocalSize() != reduced_values.size:
            raise ValueError("reduced RHS local size mismatch")
        reduced_rhs.array[:] = reduced_values
        reduced_rhs.assemble()
        if not np.isfinite(reduced_values).all() or float(reduced_rhs.norm()) <= 0.0:
            raise ValueError("retained physical RHS is zero or non-finite")
        summary["rhs"] = {
            **rhs_facts,
            "full_size": int(full_rhs.getSize()),
            "reduced_size": int(reduced_rhs.getSize()),
            "norm": float(reduced_rhs.norm()),
        }

        operator_identity = hashlib.sha256(
            json.dumps(dict(runtime.p6_action.operator_recipe), sort_keys=True).encode()
        ).hexdigest()
        def save_retained(iteration: int, vector: PETSc.Vec) -> None:
            path = directory / "retained_vectors" / f"iteration_{int(iteration):06d}.npy"
            path.parent.mkdir(exist_ok=True)
            np.save(path, np.asarray(vector.getArray(readonly=True), dtype=np.complex128), allow_pickle=False)

        def checkpoint(iteration: int, vector: PETSc.Vec, row: Mapping[str, Any]) -> None:
            iteration = int(iteration)
            if iteration in last_checkpoint:
                return
            last_checkpoint.add(iteration)
            retained_facts = write_solution_checkpoint(
                checkpoints / f"iteration_{iteration:06d}",
                vector,
                iteration=iteration,
                explicit_true_residual=float(row["original_A6_relative"]),
                input_identity_sha256=provenance["input_sha256"],
                operator_identity_sha256=operator_identity,
                physical_model_sha256=provenance["physical_model_sha256"],
                source_sha=source_sha,
                ownership=dict(
                    rank=0,
                    ownership_range=list(vector.getOwnershipRange()),
                    local_size=vector.getLocalSize(),
                    global_size=vector.getSize(),
                ),
                comm=vector.getComm(),
            )
            evaluation_facts = last_evaluation.get("facts")
            if not isinstance(evaluation_facts, Mapping) or "storage_solution" not in evaluation_facts:
                raise RuntimeError(
                    "a full-field checkpoint requires the storage solution from the same evaluate call"
                )
            full_field = _storage_vector(evaluation_facts["storage_solution"])
            try:
                full_facts = write_solution_checkpoint(
                    full_checkpoints / f"iteration_{iteration:06d}",
                    full_field,
                    iteration=iteration,
                    explicit_true_residual=float(row["original_A6_relative"]),
                    input_identity_sha256=provenance["input_sha256"],
                    operator_identity_sha256=operator_identity,
                    physical_model_sha256=provenance["physical_model_sha256"],
                    source_sha=source_sha,
                    ownership=dict(
                        rank=0,
                        ownership_range=list(full_field.getOwnershipRange()),
                        local_size=full_field.getLocalSize(),
                        global_size=full_field.getSize(),
                    ),
                    comm=full_field.getComm(),
                )
                storage_values = np.asarray(
                    evaluation_facts["storage_solution"], dtype=np.complex128
                )
                recovery_record = {
                    "schema": "task039extra.v20.retained-recovery-packet.v1",
                    "iteration": iteration,
                    "space": "full_p6_storage_with_exact_zero_MPC_slaves",
                    "source_sha": source_sha,
                    "input_sha256": provenance["input_sha256"],
                    "physical_model_sha256": provenance["physical_model_sha256"],
                    "operator_identity_sha256": operator_identity,
                    "retained_checkpoint": retained_facts,
                    "full_checkpoint": full_facts,
                    "storage_solution_sha256": hashlib.sha256(storage_values.tobytes()).hexdigest(),
                    "storage_solution_shape": [int(item) for item in storage_values.shape],
                    "original_A6_relative": float(row["original_A6_relative"]),
                    "port_closure_relative": float(row["port_closure_relative"]),
                    "internal_residual_relative": float(row["internal_residual_relative"]),
                    "native_identity_relative": float(row["native_identity_relative"]),
                    "schur_port_identity_relative": float(row["schur_port_identity_relative"]),
                    "p4_logical_apply_calls": int(runtime.p4_ledger.logical_apply_calls),
                    "p4_factor_counts": dict(runtime.p4_ledger._factor_counts()),
                    "recovery_evaluation_reused": True,
                    "full_rhs_not_duplicated": True,
                }
                _atomic_json(
                    recovery_packets / f"iteration_{iteration:06d}.json",
                    recovery_record,
                )
            finally:
                full_field.destroy()
                last_evaluation["facts"] = None

        def evaluate(target: PETSc.Vec, reduced_residual: PETSc.Vec) -> Mapping[str, Any]:
            # The raw recovery arrays belong only to the current evaluation.
            # Checkpoint code consumes them immediately; the next call must
            # not retain a second full-space packet.
            last_evaluation["facts"] = None
            facts = runtime.p6_action.evaluate_native_residual(
                target,
                full_rhs,
                _native_apply,
                rhs_is_mpc_dual=True,
                reduced_residual=reduced_residual,
            )
            last_evaluation["facts"] = facts
            return {
                **_mapped_native_residual_facts(facts),
                "native_rhs_norm": float(facts["native_rhs_norm"]),
                "port_operation_scale": float(facts["port_operation_scale"]),
                "internal_operation_scale": float(facts["internal_operation_scale"]),
                "logical_p4_count": int(runtime.p4_ledger.logical_apply_calls),
                "p4_factor_counts": dict(runtime.p4_ledger._factor_counts()),
            }

        # These are fixed trace/port/mixed algebra checks on the same D3
        # object that will enter the outer solve.  Their port residuals are
        # observations only: an arbitrary algebra vector is not a converged
        # physical solution.  The identity checks are the setup contract.
        setup_vectors = {
            "trace": np.zeros(runtime.p6_action.reduced_size, dtype=np.complex128),
            "port": np.zeros(runtime.p6_action.reduced_size, dtype=np.complex128),
            "mixed": np.zeros(runtime.p6_action.reduced_size, dtype=np.complex128),
        }
        active_rows = int(runtime.p6_system.active_rows)
        appended_rows = int(runtime.p6_system.appended_rows)
        if active_rows:
            active_index = np.arange(active_rows, dtype=np.float64) + 1.0
            active_values = np.sin(0.017 * active_index) + 1j * np.cos(0.013 * active_index)
            setup_vectors["trace"][:active_rows] = active_values
            setup_vectors["mixed"][:active_rows] = active_values
        if appended_rows:
            port_index = np.arange(appended_rows, dtype=np.float64) + 1.0
            port_values = np.sin(0.023 * port_index) - 1j * np.cos(0.019 * port_index)
            setup_vectors["port"][active_rows:] = port_values
            setup_vectors["mixed"][active_rows:] = port_values
        setup_algebra = {}
        for name, values in setup_vectors.items():
            last_evaluation["facts"] = None
            raw_facts = runtime.p6_action.evaluate_native_residual(
                values,
                full_rhs,
                _native_apply,
                rhs_is_mpc_dual=True,
                reduced_residual=None,
            )
            setup_algebra[name] = _mapped_native_residual_facts(raw_facts)
            # No checkpoint uses these setup arrays; release them before the
            # next fixed algebra vector is evaluated.
            last_evaluation["facts"] = None
            del raw_facts
        setup_logical_before = int(runtime.p4_ledger.logical_apply_calls)
        setup_factor_before = dict(runtime.p4_ledger._factor_counts())
        setup_bal_h_output = bridge.apply(reduced_values)
        setup_bal_h_facts = dict(runtime.bal_h.last_apply_facts)
        setup_logical_after = int(runtime.p4_ledger.logical_apply_calls)
        setup_factor_after = dict(runtime.p4_ledger._factor_counts())
        if setup_bal_h_output.shape != reduced_values.shape or not np.isfinite(setup_bal_h_output).all():
            raise FloatingPointError("same-object BAL_H setup check returned an invalid vector")
        setup_pc_record = {
            **setup_bal_h_facts,
            "scope": "setup",
            "setup_check": "one_actual_BAL_H_apply_two_logical_p4_calls",
            "outer_pc_apply": int(bridge.apply_count),
            "p4_logical_apply_before": setup_logical_before,
            "p4_logical_apply_after": setup_logical_after,
            "p4_logical_apply_delta": setup_logical_after - setup_logical_before,
            "p4_factor_counts_before": setup_factor_before,
            "p4_factor_counts_after": setup_factor_after,
            "p4_physical_factor_delta": {
                key: int(setup_factor_after.get(key, 0) - setup_factor_before.get(key, 0))
                for key in ("symbolic_calls", "numeric_calls", "solve_calls")
            },
            "p4_audit": dict(runtime.p4_ledger.last_audit),
        }
        ledger.append("pc_applies.jsonl", setup_pc_record)
        cache_after_setup = {
            "cache_identity": dict(runtime.p6_action.cache_identity),
            "buffer_inventory": dict(runtime.p6_action.buffer_inventory),
        }
        cache_setup_unchanged = cache_after_setup == cache_before
        algebra_pass = all(
            np.isfinite(float(algebra[key])) and float(algebra[key]) <= 1.0e-10
            for algebra in setup_algebra.values()
            for key in (
                "internal_residual_relative",
                "native_identity_relative",
                "schur_port_identity_relative",
            )
        )
        setup_checks = {
            "status": "PASS"
            if algebra_pass
            and (aq_projection_check is None or aq_projection_check["passed"])
            and setup_bal_h_facts.get("status") == "BALANCED_ACTION_COMPLETED"
            and setup_pc_record["p4_logical_apply_delta"] == 2
            and cache_setup_unchanged
            else "D2_SETUP_UNQUALIFIED",
            "same_runtime_object": True,
            "trace": {
                "active_rows": int(runtime.p6_system.active_rows),
                "full_rows": int(runtime.p6_system.full_rows),
                "trace_constraint_identity": "p6_system.trace_constraints",
            },
            "port": {
                "appended_rows": int(runtime.p6_system.appended_rows),
                "H_p_sha256": hashlib.sha256(runtime.p6_action.H_p.tobytes()).hexdigest(),
                "Hhat_sha256": hashlib.sha256(runtime.p6_action.Hhat.tobytes()).hexdigest(),
                "fixed_vector_port_residuals": {
                    name: float(values["port_closure_relative"])
                    for name, values in setup_algebra.items()
                },
                "closure_gate": "outer_solution_only",
            },
            "mixed_original_A6_J": {
                "fixed_vector_facts": setup_algebra,
                "fixed_vector_nonzero_entries": {
                    name: int(np.count_nonzero(values))
                    for name, values in setup_vectors.items()
                },
                "identity_tolerance": 1.0e-10,
                "port_residual_policy": "record_only_for_setup_vectors",
            },
            "bal_h": {
                "actual_logical_call": True,
                "bridge_apply_count": int(bridge.apply_count),
                "bal_h_callback_count": int(bridge.bal_h_count),
                "p4_audit": dict(runtime.p4_ledger.last_audit),
            },
            "cache_before": cache_before,
            "cache_after_setup": cache_after_setup,
            "cache_content_and_unique_bytes_unchanged": cache_setup_unchanged,
        }
        if aq_projection_check is not None:
            setup_checks["native_aq_projection"] = aq_projection_check
        summary["retained_runtime"]["setup_checks"] = setup_checks
        ledger.marker("retained_same_object_setup_checks_complete", setup_checks)
        if setup_checks["status"] != "PASS":
            raise RuntimeError("D2 same-object setup checks were not qualified")

        def pc(source: PETSc.Vec) -> PETSc.Vec:
            values = np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
            p4_logical_before = int(runtime.p4_ledger.logical_apply_calls)
            p4_factor_before = dict(runtime.p4_ledger._factor_counts())
            try:
                output_values = bridge.apply(values)
                output = source.duplicate()
                output.array[:] = output_values
                output.assemble()
                return output
            except BaseException:
                if "output" in locals():
                    output.destroy()
                raise
            finally:
                coupling_facts = dict(runtime.bal_h.last_apply_facts)
                coupling_facts.update(
                    {
                        "scope": "outer_pc",
                        "outer_pc_apply": int(bridge.apply_count),
                        "p4_logical_apply_before": p4_logical_before,
                        "p4_logical_apply_after": int(runtime.p4_ledger.logical_apply_calls),
                        "p4_logical_apply_delta": int(
                            runtime.p4_ledger.logical_apply_calls - p4_logical_before
                        ),
                        "p4_factor_counts_before": p4_factor_before,
                        "p4_factor_counts_after": dict(runtime.p4_ledger._factor_counts()),
                        "p4_physical_factor_delta": {
                            key: int(
                                runtime.p4_ledger._factor_counts().get(key, 0)
                                - p4_factor_before.get(key, 0)
                            )
                            for key in ("symbolic_calls", "numeric_calls", "solve_calls")
                        },
                        "p4_audit": dict(runtime.p4_ledger.last_audit),
                        "p4_logical_apply_calls": int(
                            runtime.p4_ledger.logical_apply_calls
                        ),
                    }
                )
                ledger.append("pc_applies.jsonl", coupling_facts)

        ledger.set_phase("solve")
        solve_started = time.monotonic()
        from src.solvers.physical_retained_fgmres import run_retained_fgmres

        result = run_retained_fgmres(
            reduced_rhs,
            runtime.p6_action.apply,
            pc,
            evaluate=evaluate,
            checkpoint=checkpoint,
            append=ledger.append,
            seconds=lambda: time.monotonic() - solve_started,
            resource_sample=sample,
            stop_requested=lambda: ledger.stop_signal is not None,
            save_retained=save_retained,
        )
        solve_summary = {
            key: value for key, value in result.items() if key != "final_solution"
        }
        solve_summary["p4_factor_counts"] = dict(runtime.p4_ledger._factor_counts())
        summary["solve"] = solve_summary
        summary["outer_pc_counts"] = {
            "retained_fgmres_pc_apply_count": int(result["pc_apply_count"]),
            "retained_bal_h_bridge_apply_count": int(bridge.apply_count),
            "retained_bal_h_callback_count": int(bridge.bal_h_count),
            "p4_logical_apply_calls": int(runtime.p4_ledger.logical_apply_calls),
            "p4_factor_counts": dict(runtime.p4_ledger._factor_counts()),
            "note": "18-cell build probe did not call bridge.apply; formal counts are recorded here",
        }
        cache_after_solve = {
            "cache_identity": dict(runtime.p6_action.cache_identity),
            "buffer_inventory": dict(runtime.p6_action.buffer_inventory),
        }
        summary["retained_runtime"]["p6_cache_after_solve"] = cache_after_solve
        summary["retained_runtime"]["p6_cache_unchanged_before_release"] = (
            cache_after_solve == cache_before
        )
        if result["status"] != "TRUE_RESIDUAL_PASS":
            summary["status"] = result["status"]
            raise RuntimeError(result["status"])

        reduced_solution = result["final_solution"]
        recovered = runtime.p6_action.recover_storage(
            np.asarray(reduced_solution.getArray(readonly=True), dtype=np.complex128),
            full_rhs=full_rhs,
            expand_trace=False,
        )
        saved_field = _storage_vector(recovered)
        summary["pre_release_a6"] = _a6_fact(saved_field)
        if not summary["pre_release_a6"]["finite"] or summary["pre_release_a6"]["relative"] > 1.0e-6:
            raise RuntimeError("pre-release original A6 gate failed")
        pre_packet = directory / "pre_release_residual_packet.npz"
        pre_action = apply_owned(runtime.fine["physical_action"], saved_field)
        pre_residual = full_rhs.duplicate()
        try:
            full_rhs.copy(pre_residual)
            pre_residual.axpy(PETSc.ScalarType(-1.0), pre_action)
            np.savez(
                pre_packet,
                storage_solution=np.asarray(saved_field.getArray(readonly=True), dtype=np.complex128),
                full_rhs=np.asarray(full_rhs.getArray(readonly=True), dtype=np.complex128),
                original_a6=np.asarray(pre_action.getArray(readonly=True), dtype=np.complex128),
                residual=np.asarray(pre_residual.getArray(readonly=True), dtype=np.complex128),
            )
        finally:
            pre_residual.destroy()
            pre_action.destroy()
        summary["pre_release_residual_packet"] = {
            "filename": pre_packet.name,
            "sha256": hashlib.sha256(pre_packet.read_bytes()).hexdigest(),
            "recorded_before_release": True,
            "storage_space": "full_p6_storage_with_exact_zero_MPC_slaves",
        }
        ledger.marker("retained_pre_release_packet_complete", summary["pre_release_residual_packet"])
        _atomic_json(directory / "physical_intermediate_summary.json", summary)
        release_facts = runtime.release_solver_stack(
            field_saved=True,
            pre_release_a6_checked=True,
            marker=ledger.marker,
        )
        summary["release"] = release_facts
        summary["post_release_a6"] = _a6_fact(saved_field)
        if not summary["post_release_a6"]["finite"] or summary["post_release_a6"]["relative"] > 1.0e-6:
            raise RuntimeError("post-release original A6 gate failed")
        summary["auxiliary_stack_released_before_recovery"] = True

        ledger.set_phase("recovery")

        def canonical_export(field, output_dir):
            from benchmarks.canonical_vector_artifacts import write_canonical_packet_shard
            from src.solvers.hcurl_canonical_vector_dolfinx import iter_canonical_full_fe_packets

            return write_canonical_packet_shard(
                output_dir / "canonical_solution.rank0000.jsonl",
                iter_canonical_full_fe_packets(
                    field.function_space, field, runtime.fine["setup"]["floquets"][6]
                ),
                audit_packets=True,
            )

        outputs = recover_p0_outputs(
            runtime.fine,
            saved_field,
            directory / "numerical_output",
            canonical_export=canonical_export,
            export_all_port_modes=True,
        )
        summary["official_result"] = outputs
        if profile_identity in V5_NATIVE_PROFILES:
            summary["matched_reference"] = compare_retained_v5_output(
                profile_identity,
                outputs,
                directory / "numerical_output",
                fine=runtime.fine,
                solution=saved_field,
                current_run_identity={
                    "run_id": directory.name,
                    "source_sha": source_sha,
                    "input_sha256": provenance["input_sha256"],
                    "physical_model_sha256": provenance[
                        "physical_model_sha256"
                    ],
                },
            )
        else:
            summary["matched_reference"] = compare_retained_5nm_output(
                outputs,
                directory / "numerical_output",
                fine=runtime.fine,
                solution=saved_field,
            )
        raw_path = directory / "final_residual_arrays.npz"
        action = apply_owned(runtime.fine["physical_action"], saved_field)
        try:
            np.savez(
                raw_path,
                rhs=np.asarray(full_rhs.getArray(readonly=True), dtype=np.complex128),
                action=np.asarray(action.getArray(readonly=True), dtype=np.complex128),
                solution=np.asarray(saved_field.getArray(readonly=True), dtype=np.complex128),
            )
        finally:
            action.destroy()
        summary["residual_arrays"] = {
            "filename": raw_path.name,
            "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
            "operator_identity_sha256": operator_identity,
            "input_sha256": provenance["input_sha256"],
            "physical_model_sha256": provenance["physical_model_sha256"],
        }
        summary["final_solution_sha256"] = hashlib.sha256(
            np.asarray(saved_field.getArray(readonly=True), dtype=np.complex128).tobytes()
        ).hexdigest()
        summary["status"] = "RESIDUAL_PASS"
        summary["elapsed_monotonic_seconds"] = time.monotonic() - ledger.started
        _atomic_json(directory / "physical_intermediate_summary.json", summary)
        from benchmarks.physical_intermediate_checker import check

        checked = check(directory)
        _atomic_json(directory / "checker.json", checked)
        summary["checker"] = checked
        summary["status"] = checked["classification"]
        summary["reference_authority"] = checked["reference_authority"]
        _atomic_json(directory / "physical_intermediate_summary.json", summary)
        return {
            "passed": bool(checked["independent_output_gates_passed"]),
            "errors": checked["gate_failures"],
            "summary": str(directory / "physical_intermediate_summary.json"),
            "numerical_output_directory": str(directory / "numerical_output"),
        }
    except BaseException as exc:
        p4_status = None
        if runtime is not None and runtime.p4_ledger is not None:
            p4_status = runtime.p4_ledger.last_audit.get("status")
        retained_status = (
            "P4_NUMERICAL_UNQUALIFIED"
            if p4_status == "P4_NUMERICAL_UNQUALIFIED"
            else "CONTROLLED_STOP"
            if isinstance(exc, InterruptedError)
            else "FAILED"
        )
        summary.update(
            status=retained_status,
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            failed_stage=ledger.last_stage,
            failed_phase=ledger.phase,
        )
        _atomic_json(directory / "physical_intermediate_summary.json", summary)
        raise
    finally:
        if result is not None:
            final = result.pop("final_solution", None)
            if final is not None:
                final.destroy()
        if reduced_rhs is not None:
            reduced_rhs.destroy()
        if full_rhs is not None:
            full_rhs.destroy()
        if saved_field is not None:
            saved_field.destroy()
        if runtime is not None:
            runtime.destroy()

__all__ = [
    "RetainedCondensedRuntime",
    "persist_p4_failure_packet",
    "run_retained_condensed_workflow",
]
