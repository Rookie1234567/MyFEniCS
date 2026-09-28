"""Task042 original p4 operator without constructing a p6 numerical stack.

Used only after a full real F1 native A4=PH A6 P/interface qualification.
Same geometry/MPC/ports/quadrature and row-stream CSR SHA must match F1.
"""

from dataclasses import dataclass

from dolfinx import fem

from src.runners.physical_retained_condensed_v20 import _support_groups
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    build_same_mesh_physical_action,
    destroy_same_mesh_physical_action,
)
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.p4_cell_condensed_inverse import (
    assemble_condensed_ports,
    petsc_csr_content_identity,
)
from src.solvers.p6_cell_condensed_action import (
    build_p6_cell_condensed_action_from_carrier,
)


@dataclass
class OriginalP4Runtime:
    levels: dict
    p4: dict
    p4_system: object
    action: object
    operator_identity: dict
    global_p4_factor_created: bool = False

    @classmethod
    def build(cls, cfg, comm, *, quadrature, expected_sha, marker=lambda *_: None):
        if comm.size != 1:
            raise ValueError("MPI1 required")
        levels = _build_same_mesh_levels(
            cfg, comm, (4,), include_positive_coefficients=False
        )
        marker("original_p4_mesh_complete", {})
        p4 = build_same_mesh_physical_action(
            levels, cfg, 4, volume_quadrature_metadata=tuple(quadrature)
        )
        system = action = None
        try:
            carrier = p4["dtn_action"].carrier
            groups, group_by_row = _support_groups(levels["spaces"][4], carrier)
            compiled = fem.form(p4["volume_action"].bilinear_form)
            system = build_unconstrained_assembly_time_condensation(
                compiled,
                levels["spaces"][4],
                levels["mesh_data"].cell_tags,
                mpc=levels["floquets"][4].mpc,
                appended_global_rows=len(carrier.entries),
                appended_support_owned_cell_groups=groups,
                appended_support_group_by_row=group_by_row,
                materialize_global_matrix=True,
                retain_local_schur_for_matrix_free=True,
                dense_appended_block=True,
                sum_duplicate_cell_integrals=True,
                strict_local_checks=True,
                defer_final_assembly=True,
                geometry_identity_policy="raw_unrounded",
                share_identity_cache=True,
            )
            assemble_condensed_ports(system, carrier)
            system.matrix.assemble()
            identity = petsc_csr_content_identity(system.matrix)
            if identity["csr_sha256"] != expected_sha:
                raise ValueError("Original p4 content differs from qualified F1")
            action = build_p6_cell_condensed_action_from_carrier(
                system, carrier, owns_condensed=False, borrowed_p4_witness=True
            )
            marker("original_p4_without_p6_stack_built", identity)
            return cls(levels, p4, system, action, identity)
        except BaseException:
            if action is not None:
                action.destroy()
            if system is not None:
                system.destroy()
            destroy_same_mesh_physical_action(p4)
            levels.clear()
            raise

    def destroy(self):
        self.action.destroy()
        self.p4_system.destroy()
        destroy_same_mesh_physical_action(self.p4)
        self.levels.clear()
