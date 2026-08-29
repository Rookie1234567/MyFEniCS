"""Selected same-mesh p6 physical Maxwell action and recovery helpers.

The positive p6/p3/p1 bundle remains the auxiliary preconditioner.  This
module adds only the physical p6 volume form and the streaming Fourier-DtN
action on the very same mesh, without assembling a p6 matrix or creating a
physical KSP.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np


PHYSICAL_BUNDLE_SCHEMA = "task038.same_mesh_hcurl_pmg.physical.v1"
PHYSICAL_PROFILE = "same_mesh_hcurl_pmg_v1_requalified"


def _notify_stage(
    callback: Callable[[str, Mapping[str, Any]], None] | None,
    name: str,
    facts: Mapping[str, Any],
) -> None:
    if callback is not None:
        callback(name, dict(facts))


def _surface_assemblers(
    function_space: Any,
    mesh_data: Any,
    cfg: Any,
    qdegree: int,
    *,
    jit_options: Mapping[str, Any] | None = None,
) -> dict[tuple[str, int], Any]:
    from .dtn_port_3d import _ReusableSurfaceComponentAssembler

    return {
        (side, component): _ReusableSurfaceComponentAssembler(
            function_space,
            mesh_data,
            cfg.tags.z_max if side == "top" else cfg.tags.z_min,
            component,
            quadrature_degree=qdegree,
            jit_options=jit_options,
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }


def build_p6_same_mesh_physical_bundle(
    cfg: Any,
    comm: Any,
    *,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Attach the exact p6 volume+DtN operator to the selected positive setup."""

    from .fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from .fullspace_mpc_action import build_fullspace_mpc_form_action
    from .fullspace_physical_action import FullspacePhysicalAction
    from .fullspace_same_mesh_hcurl_pmg_setup import (
        SAME_MESH_JIT_OPTIONS,
        build_p6_same_mesh_setup,
    )
    from .common_3d_forms import _build_variational_forms
    from .dtn_port_3d import _dtn_surface_quadrature_degree
    from .dtn_port_3d import _incident_projection_onto_top_mode

    if int(comm.size) != 1:
        raise ValueError("the P0 physical lane is fixed to MPI1")
    _notify_stage(stage_callback, "positive_setup_started", {"levels": [6, 3, 1]})
    setup = build_p6_same_mesh_setup(cfg, comm)
    dtn_action = None
    volume_action = None
    physical_action = None
    try:
        _notify_stage(
            stage_callback,
            "positive_setup_complete",
            {"levels": [6, 3, 1], "profile": PHYSICAL_PROFILE},
        )
        _notify_stage(stage_callback, "mode_inventory_started", {})
        modes, mode_rows, mode_sha = build_dynamic_mode_inventory(cfg)
        qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
        _notify_stage(
            stage_callback,
            "mode_inventory_complete",
            {
                "mode_count": int(len(modes)),
                "mode_manifest_sha256": str(mode_sha),
                "dtn_quadrature_degree": int(qdegree),
            },
        )
        p6_space = setup["spaces"][6]
        p6_floquet = setup["floquets"][6]
        _notify_stage(stage_callback, "surface_assemblers_started", {"count": 4})
        assemblers = _surface_assemblers(
            p6_space,
            setup["mesh_data"],
            cfg,
            qdegree,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        _notify_stage(
            stage_callback,
            "surface_assemblers_complete",
            {"count": int(len(assemblers))},
        )
        _notify_stage(
            stage_callback,
            "dtn_carrier_started",
            {"mode_count": int(len(modes))},
        )
        carrier = build_fullspace_dtn_carrier_from_surface(
            modes, assemblers, p6_floquet.mpc, cfg
        )
        _notify_stage(
            stage_callback,
            "dtn_carrier_complete",
            {"mode_count": int(len(modes)), "surface_assembler_count": int(len(assemblers))},
        )
        dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
        _notify_stage(
            stage_callback,
            "dtn_action_complete",
            {"mode_count": int(len(modes))},
        )
        del carrier, assemblers

        _notify_stage(
            stage_callback,
            "physical_volume_action_started",
            {"form": "exact_maxwell_volume"},
        )
        bilinear, _rhs_form = _build_variational_forms(
            setup["mesh_data"].mesh,
            setup["mesh_data"],
            cfg,
            p6_space,
            field_formulation="total_field",
        )
        volume_action = build_fullspace_mpc_form_action(
            bilinear,
            p6_space,
            mpc=p6_floquet.mpc,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        _notify_stage(
            stage_callback,
            "physical_volume_action_complete",
            {"form": "exact_maxwell_volume", "volume_action": True},
        )
        physical_action = FullspacePhysicalAction(volume_action, dtn_action)
        owned_volume_action = volume_action
        owned_dtn_action = dtn_action
        volume_action = None
        dtn_action = None
        incident_projections = tuple(
            _incident_projection_onto_top_mode(mode, cfg) for mode in modes
        )
        bundle = {
            "schema": PHYSICAL_BUNDLE_SCHEMA,
            "profile": PHYSICAL_PROFILE,
            "setup": setup,
            "cfg": cfg,
            "physical_action": physical_action,
            "dtn_action": owned_dtn_action,
            "volume_action": owned_volume_action,
            "modes": tuple(modes),
            "mode_rows": tuple(mode_rows),
            "mode_sha256": str(mode_sha),
            "incident_projections": incident_projections,
            "dtn_quadrature_degree": int(qdegree),
        }
        _notify_stage(
            stage_callback,
            "bundle_built",
            {
                "levels": [6, 3, 1],
                "mode_count": int(len(modes)),
                "physical_action": True,
            },
        )
        return bundle
    except Exception:
        if physical_action is not None:
            physical_action.destroy()
        else:
            if dtn_action is not None:
                dtn_action.destroy()
            if volume_action is not None:
                volume_action.destroy()
        from .fullspace_same_mesh_hcurl_pmg_setup import (
            destroy_p6_same_mesh_setup_bundle,
        )

        destroy_p6_same_mesh_setup_bundle(setup)
        raise


def audit_p6_same_mesh_physical_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """Return setup and physical action facts without creating a source/KSP."""

    from .fullspace_same_mesh_hcurl_pmg_setup import audit_p6_same_mesh_setup

    setup_audit = audit_p6_same_mesh_setup(bundle["setup"])
    physical_audit = dict(bundle["physical_action"].audit)
    physical_audit.update(
        {
            "mode_manifest_sha256": str(bundle["mode_sha256"]),
            "mode_count": int(len(bundle["modes"])),
            "dtn_quadrature_degree": int(bundle["dtn_quadrature_degree"]),
            "physical_form": "exact_maxwell_volume_plus_streaming_fourier_dtn",
        }
    )
    return {
        "schema": PHYSICAL_BUNDLE_SCHEMA,
        "profile": PHYSICAL_PROFILE,
        "setup_audit": setup_audit,
        "physical_action": physical_audit,
        "architecture": {
            "levels": [6, 3, 1],
            "same_physical_mesh": True,
            "p6_matrix_free": True,
            "p6_global_aij": False,
            "high_order_global_aij": False,
            "p3_sparse_allowed": True,
            "p1_sparse_allowed": True,
            "global_dense_transfer": False,
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "p6_factor": False,
            "outer_ksp_created": True,
            "physical_solve": True,
            "dtn": True,
            "recovery": True,
            "source_is_pde_rhs": True,
        },
    }


def build_physical_rhs(bundle: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    """Build the current dtn-port physical RHS, without applying the operator."""

    from .dtn_port_3d import _assemble_mpc_vector, _incident_top_traction_form
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    setup = bundle["setup"]
    cfg = bundle["cfg"]
    p6_space = setup["spaces"][6]
    floquet = setup["floquets"][6]
    base = _assemble_mpc_vector(
        _incident_top_traction_form(p6_space, setup["mesh_data"], cfg),
        floquet.mpc,
        quadrature_degree=int(bundle["dtn_quadrature_degree"]),
        jit_options=SAME_MESH_JIT_OPTIONS,
    )
    rhs = base.duplicate()
    try:
        bundle["physical_action"].compose_physical_rhs(
            base,
            bundle["incident_projections"],
            rhs,
        )
    finally:
        base.destroy()
    return rhs, {
        "generation": "dtn_port_modal_physical_rhs",
        "role": "physical_maxwell_rhs",
        "phase_application": "finalized_floquet_mpc_once",
        "mode_count": int(len(bundle["modes"])),
        "mode_manifest_sha256": str(bundle["mode_sha256"]),
    }


def recover_p0_outputs(
    bundle: Mapping[str, Any], solution: Any, output_dir: Path
) -> dict[str, Any]:
    """Recover E/H and compute the existing modal and diagnostic outputs."""

    from dolfinx import fem
    from ..postprocessing.diffraction_3d import compute_diffraction_orders_3d
    from ..postprocessing.postprocess_3d import save_airbox_3d_fields
    from ..postprocessing.rta_3d import compute_volume_absorption_3d
    from .dtn_port_3d import _port_power_metrics
    from ..common.modes_3d import incident_power_3d

    setup = bundle["setup"]
    floquet = setup["floquets"][6]
    field = fem.Function(floquet.mpc.function_space, name="E_total")
    try:
        solution.copy(field.x.petsc_vec)
        field.x.scatter_forward()
        floquet.mpc.homogenize(field)
        field.x.scatter_forward()
        floquet.mpc.backsubstitution(field)
        field.x.scatter_forward()
        recovered_auxiliary = bundle["dtn_action"].recover_auxiliary(solution)
        aux = np.asarray(recovered_auxiliary, dtype=np.complex128)
        del recovered_auxiliary
        port_metrics = _port_power_metrics(
            bundle["cfg"],
            list(bundle["modes"]),
            aux,
            list(bundle["incident_projections"]),
        )
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        field_export = save_airbox_3d_fields(
            setup["mesh_data"], bundle["cfg"], field, output_dir
        )
        volume_metrics = compute_volume_absorption_3d(
            setup["mesh_data"],
            bundle["cfg"],
            field,
            output_dir,
            incident_power=incident_power_3d(bundle["cfg"]),
            port_metrics=port_metrics,
        )
        diffraction_metrics = compute_diffraction_orders_3d(
            setup["mesh_data"], bundle["cfg"], field, output_dir
        )
        return {
            "field_model": "total_field",
            "electric_finite": bool(np.all(np.isfinite(field.x.array))),
            "auxiliary_finite": bool(np.all(np.isfinite(aux))),
            "auxiliary": aux,
            "port_metrics": port_metrics,
            "volume_metrics": volume_metrics,
            "diffraction_metrics": diffraction_metrics,
            "diffraction_channel_count": int(
                diffraction_metrics["diffraction_channel_count"]
            ),
            "field_export": field_export,
        }
    finally:
        del field


def release_p6_same_mesh_solver_stack(bundle: dict[str, Any]) -> None:
    """Release only the auxiliary hierarchy, preserving physical recovery state."""

    setup = bundle["setup"]
    upper = setup.pop("upper_cycle", None)
    if upper is not None:
        upper.destroy()
    for name in (
        "lower_cycle",
        "p63_owner_transfer",
        "p31_owner_transfer",
        "p6_shell",
        "p63_local_transfer",
        "p31_local_transfer",
    ):
        setup.pop(name, None)
    for name in ("p3_matrix", "p1_matrix"):
        matrix = setup.pop(name, None)
        if matrix is not None:
            matrix.destroy()


def destroy_p6_same_mesh_physical_bundle(bundle: dict[str, Any]) -> None:
    """Destroy physical action first, then the selected setup bundle once."""

    if not bundle:
        return
    physical = bundle.pop("physical_action", None)
    setup = bundle.pop("setup", None)
    if physical is not None:
        physical.destroy()
    if setup:
        from .fullspace_same_mesh_hcurl_pmg_setup import (
            destroy_p6_same_mesh_setup_bundle,
        )

        destroy_p6_same_mesh_setup_bundle(setup)
    bundle.clear()


__all__ = (
    "PHYSICAL_BUNDLE_SCHEMA",
    "PHYSICAL_PROFILE",
    "audit_p6_same_mesh_physical_bundle",
    "build_p6_same_mesh_physical_bundle",
    "build_physical_rhs",
    "destroy_p6_same_mesh_physical_bundle",
    "release_p6_same_mesh_solver_stack",
    "recover_p0_outputs",
)
