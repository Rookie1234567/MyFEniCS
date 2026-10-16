"""Selected same-mesh p6 physical Maxwell action and recovery helpers.

The positive p6/p3/p1 bundle remains the auxiliary preconditioner.  This
module adds only the physical p6 volume form and the streaming Fourier-DtN
action on the very same mesh, without assembling a p6 matrix or creating a
physical KSP.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np

from .dtn_sparse_policy import (
    LEGACY_DTN_SPARSE_CUTOFF_POLICY,
    normalize_dtn_sparse_cutoff_policy,
)


PHYSICAL_BUNDLE_SCHEMA = "task038.same_mesh_hcurl_pmg.physical.v2"
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
    mpc: Any | None = None,
    surface_assembly_backend: str | None = None,
    reuse_surface_geometry_cache: bool = False,
    surface_geometry_cache_limit_bytes: int = 0,
    surface_weighted_moment_contraction: str | None = None,
    prepare_surface_trace_contraction: bool = False,
    jit_options: Mapping[str, Any] | None = None,
) -> dict[tuple[str, int], Any]:
    from .dtn_port_3d import _ReusableSurfaceComponentAssembler

    if surface_weighted_moment_contraction is not None and surface_assembly_backend is None:
        raise ValueError(
            "weighted-moment contraction requires an explicit Legendre surface backend"
        )
    if surface_assembly_backend is not None:
        from .dtn_port_3d import (
            _SurfaceLegendreMomentAssembler,
            _SurfaceLegendreMomentContext,
        )
        from .fullspace_surface_legendre import (
            SURFACE_COMPONENT_PAIR_BACKEND,
            SURFACE_LEGENDRE_BACKEND,
            SURFACE_POINTWISE_WEIGHTED_BACKEND,
        )

        if surface_assembly_backend not in {
            SURFACE_LEGENDRE_BACKEND,
            SURFACE_POINTWISE_WEIGHTED_BACKEND,
            SURFACE_COMPONENT_PAIR_BACKEND,
        }:
            raise ValueError(
                f"unsupported explicit surface assembly backend: {surface_assembly_backend}"
            )
        if mpc is None:
            raise ValueError("Legendre surface assembly requires the finalized MPC")
        context = _SurfaceLegendreMomentContext(
            function_space,
            mesh_data,
            mpc,
            cfg,
            int(qdegree),
            backend=surface_assembly_backend,
            reuse_geometry_cache=reuse_surface_geometry_cache,
            geometry_cache_limit_bytes=surface_geometry_cache_limit_bytes,
            weighted_moment_contraction=surface_weighted_moment_contraction,
            prepare_trace_contraction=prepare_surface_trace_contraction,
        )
        return {
            (side, component): _SurfaceLegendreMomentAssembler(
                context,
                side,
                cfg.tags.z_max if side == "top" else cfg.tags.z_min,
                component,
            )
            for side in ("top", "bottom")
            for component in (0, 1)
        }
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


def _build_split_volume_action(
    mesh_data: Any,
    cfg: Any,
    function_space: Any,
    floquet: Any,
    *,
    jit_options: Mapping[str, Any],
    native_curl_codegen: bool = False,
    volume_quadrature_metadata: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None,
) -> Any:
    import ufl

    from .common_3d_forms import _build_physical_volume_terms
    from .fullspace_physical_action import FullspaceSplitVolumeAction

    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure(
        "dx", domain=mesh_data.mesh, subdomain_data=mesh_data.cell_tags
    )
    curl_curl, material_mass = _build_physical_volume_terms(cfg, u, v, dx)
    if volume_quadrature_metadata is not None:
        curl_curl, material_mass = tuple(
            ufl.Form(tuple(integral.reconstruct(metadata={
                **integral.metadata(), **metadata,
            }) for integral in form.integrals()))
            for form, metadata in zip((curl_curl, material_mass), volume_quadrature_metadata, strict=True)
        )
    return FullspaceSplitVolumeAction(
        curl_curl,
        material_mass,
        function_space,
        mpc=floquet.mpc,
        jit_options=jit_options,
        **({'native_curl_codegen': True} if native_curl_codegen else {}),
    )


def build_same_mesh_physical_action(
    setup: Mapping[str, Any],
    cfg: Any,
    degree: int,
    *,
    mode_inventory: tuple[Any, Any, Any] | None = None,
    quadrature_mode_inventory: tuple[Any, Any, Any] | None = None,
    operator_selection: Mapping[str, Any] | None = None,
    selected_parent_indices: tuple[int, ...] | None = None,
    jit_options: Mapping[str, Any] | None = None,
    volume_quadrature_metadata: tuple[Mapping[str, Any], Mapping[str, Any]] | None = None,
    reuse_surface_vector: bool = False,
    reuse_surface_geometry_cache: bool = False,
    surface_geometry_cache_limit_bytes: int = 0,
    surface_weighted_moment_contraction: str | None = None,
    prepare_surface_trace_contraction: bool = False,
    functional_store_config: Mapping[str, Any] | None = None,
    surface_assembly_backend: str | None = None,
    sparse_cutoff_policy: str = LEGACY_DTN_SPARSE_CUTOFF_POLICY,
    sparse_cutoff_relative_tolerance: float = 1.0e-13,
    collect_surface_timings: bool = False,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    surface_progress_interval: int = 1024,
) -> dict[str, Any]:
    """Build one physical action from an existing same-mesh level.

    ``setup`` owns the mesh, tags, spaces, and finalized Floquet MPCs.  This
    helper only creates the requested degree's split volume action and
    streaming DtN carrier; the temporary surface assemblers are released as
    soon as the carrier has copied their owner-local functionals.  The
    returned action bundle owns the composite action and must be released with
    :func:`destroy_same_mesh_physical_action`.
    """

    from .common_3d_forms import _validate_physical_split_profile
    from .dtn_port_3d import _dtn_surface_quadrature_degree
    from .dtn_port_3d import _incident_projection_onto_top_mode
    from .fullspace_surface_legendre import SURFACE_WEIGHTED_MOMENT_CONTRACTIONS
    from .fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from .fullspace_physical_action import FullspacePhysicalAction
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    degree = int(degree)
    sparse_cutoff_policy = normalize_dtn_sparse_cutoff_policy(
        sparse_cutoff_policy
    )
    sparse_cutoff_relative_tolerance = float(sparse_cutoff_relative_tolerance)
    if (
        not np.isfinite(sparse_cutoff_relative_tolerance)
        or not 0.0 < sparse_cutoff_relative_tolerance < 1.0
    ):
        raise ValueError("same-mesh sparse cutoff relative tolerance is invalid")
    if collect_surface_timings and not reuse_surface_vector:
        raise ValueError("surface timing requires the reused-vector opt-in")
    if surface_assembly_backend is not None and not reuse_surface_vector:
        raise ValueError("opt-in surface backend requires the reused-vector path")
    if reuse_surface_geometry_cache and (
        degree != 6
        or not reuse_surface_vector
        or int(surface_geometry_cache_limit_bytes) != 4 * 1024**3
        or surface_assembly_backend
        != "q160_affine_hex_pointwise_weighted_legendre_component_pair_v1"
    ):
        raise ValueError(
            "surface geometry caching requires the explicit p6 paired backend and reused-vector path"
        )
    if not reuse_surface_geometry_cache and int(surface_geometry_cache_limit_bytes) != 0:
        raise ValueError("surface geometry cache limit requires its explicit p6 opt-in")
    if prepare_surface_trace_contraction and (
        degree != 6
        or not reuse_surface_geometry_cache
        or surface_assembly_backend
        != "q160_affine_hex_pointwise_weighted_legendre_component_pair_v1"
        or surface_weighted_moment_contraction
        not in SURFACE_WEIGHTED_MOMENT_CONTRACTIONS
    ):
        raise ValueError(
            "prepared trace contraction requires the explicit cached p6 weighted q160 route"
        )
    if functional_store_config is not None:
        if (
            degree not in (3, 6)
            or not reuse_surface_vector
            or (
                degree == 6
                and (
                    not prepare_surface_trace_contraction
                    or not reuse_surface_geometry_cache
                )
            )
        ):
            raise ValueError(
                "functional-store opt-in requires the explicit p6 prepared route or p3 native route"
            )
        required_store_keys = {
            "root",
            "source_sha256",
            "resolved_config_sha256",
            "input_sha256",
            "physical_model_sha256",
            "max_shard_working_bytes",
            "max_total_disk_bytes",
            "disk_reserve_bytes",
            "producer_provenance",
        }
        if required_store_keys.difference(functional_store_config):
            raise ValueError("functional-store configuration is incomplete")
        from pathlib import Path

        if not Path(functional_store_config["root"]).is_absolute():
            raise ValueError("functional-store root must be an absolute path")
    if int(surface_progress_interval) <= 0:
        raise ValueError("surface progress interval must be positive")
    _validate_physical_split_profile(cfg)
    try:
        function_space = setup["spaces"][degree]
        floquet = setup["floquets"][degree]
    except KeyError as exc:
        raise ValueError(f"same-mesh setup has no requested degree {degree}") from exc
    if getattr(floquet, "mpc", None) is None:
        raise ValueError("same-mesh physical action requires a finalized Floquet MPC")

    if mode_inventory is None:
        if reuse_surface_vector and stage_callback is not None:
            stage_callback("physical_mode_inventory_started", {"space_degree": degree})
        modes, mode_rows, mode_sha = build_dynamic_mode_inventory(cfg)
        if reuse_surface_vector and stage_callback is not None:
            stage_callback(
                "physical_mode_inventory_complete",
                {
                    "space_degree": degree,
                    "mode_count": int(len(modes)),
                    "mode_sha256": str(mode_sha),
                    "inventory_generated_here": True,
                },
            )
    else:
        if len(mode_inventory) != 3:
            raise ValueError("mode_inventory must contain modes, rows, and SHA")
        modes, mode_rows, mode_sha = mode_inventory
        modes = tuple(modes)
        mode_rows = tuple(mode_rows)
        mode_sha = str(mode_sha)
        if reuse_surface_vector and stage_callback is not None:
            stage_callback(
                "physical_mode_inventory_reused",
                {
                    "space_degree": degree,
                    "mode_count": int(len(modes)),
                    "mode_sha256": str(mode_sha),
                    "inventory_generated_here": False,
                },
            )
    modes = tuple(modes)
    if not modes or len(mode_rows) != len(modes):
        raise ValueError("same-mesh physical mode inventory is incomplete")
    options = SAME_MESH_JIT_OPTIONS if jit_options is None else jit_options
    if quadrature_mode_inventory is None:
        if operator_selection is not None:
            raise ValueError(
                "operator selection requires its explicit parent quadrature inventory"
            )
        if selected_parent_indices is not None:
            raise ValueError(
                "selected parent indices require an operator selection identity"
            )
        quadrature_modes = modes
        quadrature_mode_count = len(modes)
        quadrature_mode_sha = mode_sha
        parent_mode_rows = tuple(mode_rows)
    else:
        if len(quadrature_mode_inventory) != 3:
            raise ValueError("quadrature_mode_inventory must contain modes, rows, and SHA")
        quadrature_modes, quadrature_rows, quadrature_mode_sha = quadrature_mode_inventory
        quadrature_modes = tuple(quadrature_modes)
        quadrature_rows = tuple(quadrature_rows)
        parent_mode_rows = tuple(quadrature_rows)
        quadrature_mode_sha = str(quadrature_mode_sha)
        if not quadrature_modes or len(quadrature_modes) != len(quadrature_rows):
            raise ValueError("quadrature parent inventory is incomplete")
        if operator_selection is None:
            raise ValueError("a distinct quadrature inventory requires an operator selection identity")
        if (
            int(operator_selection.get("parent_mode_count", -1)) != len(quadrature_modes)
            or operator_selection.get("parent_mode_sha256") != quadrature_mode_sha
            or int(operator_selection.get("active_mode_count", -1)) != len(modes)
            or operator_selection.get("active_mode_sha256") != mode_sha
        ):
            raise ValueError("active and quadrature inventories do not match operator selection")
        if selected_parent_indices is None:
            raise ValueError("operator selection requires its exact parent index map")
        selected_parent_indices = tuple(int(index) for index in selected_parent_indices)
        if (
            len(selected_parent_indices) != len(modes)
            or any(
                index < 0 or index >= len(quadrature_modes)
                for index in selected_parent_indices
            )
            or any(
                right <= left
                for left, right in pairwise(selected_parent_indices)
            )
        ):
            raise ValueError("operator selection parent indices are invalid")
        expected_parent_indices = tuple(
            index
            for index, row in enumerate(parent_mode_rows)
            if int(row.get("n", -1)) == 0
        )
        if selected_parent_indices != expected_parent_indices:
            raise ValueError("operator selection indices are not the live n=0 rows")
        for active_index, parent_index in enumerate(selected_parent_indices):
            parent_row = dict(parent_mode_rows[parent_index])
            parent_row["mode_index"] = active_index
            if parent_row != dict(mode_rows[active_index]):
                raise ValueError(
                    "active mode row differs from its selected parent mode row"
                )
        import hashlib
        import json

        index_sha = hashlib.sha256(
            json.dumps(
                list(selected_parent_indices),
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()
        if index_sha != operator_selection.get("selected_parent_indices_sha256"):
            raise ValueError("operator selection parent-index hash differs")
        quadrature_mode_count = len(quadrature_modes)
    qdegree = _dtn_surface_quadrature_degree(cfg, list(quadrature_modes))
    if surface_weighted_moment_contraction is not None:
        from .fullspace_surface_legendre import validate_weighted_moment_contraction

        validate_weighted_moment_contraction(
            surface_weighted_moment_contraction,
            backend=surface_assembly_backend or "",
            degree=degree,
            quadrature_degree=qdegree,
            reuse_geometry_cache=reuse_surface_geometry_cache,
        )
    if (
        reuse_surface_vector
        and stage_callback is not None
        and surface_assembly_backend is None
    ):
        stage_callback(
            "physical_surface_forms_compile_started",
            {"space_degree": degree, "form_count": 4, "quadrature_degree": int(qdegree)},
        )
    assemblers = _surface_assemblers(
        function_space,
        setup["mesh_data"],
        cfg,
        qdegree,
        mpc=floquet.mpc,
        surface_assembly_backend=surface_assembly_backend,
        reuse_surface_geometry_cache=reuse_surface_geometry_cache,
        surface_geometry_cache_limit_bytes=surface_geometry_cache_limit_bytes,
        surface_weighted_moment_contraction=surface_weighted_moment_contraction,
        prepare_surface_trace_contraction=prepare_surface_trace_contraction,
        jit_options=options,
    )
    if (
        reuse_surface_vector
        and stage_callback is not None
        and surface_assembly_backend is None
    ):
        stage_callback(
            "physical_surface_forms_compile_complete",
            {"space_degree": degree, "form_count": len(assemblers), "quadrature_degree": int(qdegree)},
        )
    if surface_assembly_backend is not None and stage_callback is not None:
        context = next(iter(assemblers.values())).context
        stage_callback(
            "physical_surface_legendre_backend_ready",
            {
                "space_degree": degree,
                "form_count": len(assemblers),
                "backend": surface_assembly_backend,
                "context_facts": dict(context.facts),
            },
        )
    carrier = None
    dtn_action = None
    volume_action = None
    physical_action = None
    try:
        if reuse_surface_vector and stage_callback is not None:
            stage_callback(
                "physical_surface_carrier_build_started",
                {
                    "space_degree": degree,
            "mode_count": int(len(modes)),
            "mode_sha256": str(mode_sha),
            "quadrature_mode_count": int(quadrature_mode_count),
            "quadrature_mode_sha256": str(quadrature_mode_sha),
                    "scratch_vectors_shared_across_forms": 1,
                },
            )
        carrier = build_fullspace_dtn_carrier_from_surface(
            modes,
            assemblers,
            floquet.mpc,
            cfg,
            reuse_surface_vector=reuse_surface_vector,
            reuse_surface_geometry_cache=reuse_surface_geometry_cache,
            collect_surface_timings=collect_surface_timings,
            stage_callback=stage_callback if reuse_surface_vector else None,
            degree=degree,
            progress_interval=surface_progress_interval,
            quadrature_degree=qdegree,
            functional_store_config=functional_store_config,
            operator_selection=operator_selection,
            parent_mode_rows=(
                parent_mode_rows if operator_selection is not None else None
            ),
            selected_parent_indices=(
                selected_parent_indices if operator_selection is not None else None
            ),
            sparse_cutoff_policy=sparse_cutoff_policy,
            sparse_cutoff_relative_tolerance=sparse_cutoff_relative_tolerance,
        )
        if reuse_surface_vector and stage_callback is not None:
            completion_facts = {
                "space_degree": degree,
                "mode_count": int(len(modes)),
                "mode_sha256": str(mode_sha),
            }
            if reuse_surface_geometry_cache:
                completion_facts["surface_geometry_cache"] = (
                    next(iter(assemblers.values())).context.geometry_cache_facts()
                )
            stage_callback(
                "physical_surface_carrier_build_complete",
                completion_facts,
            )
    finally:
        # The carrier owns copied sparse functionals; assemblers own only the
        # temporary compiled surface forms and their phase constants.
        del assemblers
    try:
        dtn_action = build_fullspace_dtn_action(
            carrier, comm=setup["mesh"].comm
        )
        volume_action = _build_split_volume_action(
            setup["mesh_data"],
            cfg,
            function_space,
            floquet,
            jit_options=options,
            volume_quadrature_metadata=volume_quadrature_metadata,
            **({'native_curl_codegen': True} if degree in (4, 6) and setup.get('native_curl_jit') else {}),
        )
        physical_action = FullspacePhysicalAction(volume_action, dtn_action)
        owned_volume_action = volume_action
        owned_dtn_action = dtn_action
        dtn_action = None
        volume_action = None
        incident_projections = tuple(
            _incident_projection_onto_top_mode(mode, cfg) for mode in modes
        )
        return {
            "schema": "task038.same_mesh_hcurl_pmg.physical-action.v1",
            "setup": setup,
            "cfg": cfg,
            "degree": degree,
            "action": physical_action,
            "physical_action": physical_action,
            "volume_action": owned_volume_action,
            "dtn_action": owned_dtn_action,
            "modes": modes,
            "mode_rows": mode_rows,
            "mode_sha256": mode_sha,
            "dtn_quadrature_degree": int(qdegree),
            "dtn_sparse_cutoff_policy": sparse_cutoff_policy,
            "dtn_sparse_cutoff_relative_tolerance": (
                sparse_cutoff_relative_tolerance
            ),
            "dtn_sparse_cutoff_identity_sha256": str(
                carrier.audit["sparse_cutoff_identity_sha256"]
            ),
            "volume_quadrature_metadata": volume_quadrature_metadata,
            "incident_projections": incident_projections,
        }
    except Exception:
        if physical_action is not None:
            physical_action.destroy()
        else:
            if dtn_action is not None:
                dtn_action.destroy()
            if volume_action is not None:
                volume_action.destroy()
        raise


def destroy_same_mesh_physical_action(bundle: dict[str, Any]) -> None:
    """Destroy one action bundle without touching its borrowed setup."""

    if not bundle:
        return
    action = bundle.pop("action", None)
    if action is not None:
        action.destroy()
    bundle.clear()


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
    from .fullspace_physical_action import FullspacePhysicalAction
    from .fullspace_same_mesh_hcurl_pmg_setup import (
        SAME_MESH_JIT_OPTIONS,
        build_p6_same_mesh_setup,
    )
    from .common_3d_forms import _validate_physical_split_profile
    from .dtn_port_3d import _dtn_surface_quadrature_degree
    from .dtn_port_3d import _incident_projection_onto_top_mode

    if int(comm.size) != 1:
        raise ValueError("the P0 physical lane is fixed to MPI1")
    _validate_physical_split_profile(cfg)
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
            {
                "form": "exact_maxwell_volume_split",
                "component_count": 2,
                "components": ["curl_curl", "complex_material_mass"],
            },
        )
        volume_action = _build_split_volume_action(
            setup["mesh_data"],
            cfg,
            p6_space,
            p6_floquet,
            jit_options=SAME_MESH_JIT_OPTIONS,
        )
        _notify_stage(
            stage_callback,
            "physical_volume_action_complete",
            {
                "form": "exact_maxwell_volume_split",
                "component_count": 2,
                "components": ["curl_curl", "complex_material_mass"],
                "volume_action": True,
            },
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
            "degree": 6,
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
                "volume_component_count": 2,
                "volume_components": ["curl_curl", "complex_material_mass"],
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
            "physical_form": (
                "exact_maxwell_split_volume_plus_unchanged_streaming_fourier_dtn"
            ),
            "volume_component_count": 2,
            "volume_components": ["curl_curl", "complex_material_mass"],
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
    degree = int(bundle["degree"])
    space = setup["spaces"][degree]
    floquet = setup["floquets"][degree]
    base = _assemble_mpc_vector(
        _incident_top_traction_form(space, setup["mesh_data"], cfg),
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
        "degree": degree,
        "phase_application": "finalized_floquet_mpc_once",
        "mode_count": int(len(bundle["modes"])),
        "mode_manifest_sha256": str(bundle["mode_sha256"]),
    }


def _active_fe_port_output_identity(
    contract: Mapping[str, Any],
    *,
    active_mode_count: int,
    active_mode_sha256: str,
    sparse_cutoff_policy: str,
    sparse_cutoff_relative_tolerance: float,
    sparse_cutoff_identity_sha256: str,
) -> dict[str, Any]:
    """Validate an explicit finite-element port-output scope and its identities.

    This is intentionally separate from the legacy V7 N0-only output switch.
    It records values produced by the active FE DtN carrier and never claims
    omitted parent channels were computed.
    """

    import re

    if contract.get("schema") != "task40.active_fe_port_outputs.v2":
        raise ValueError("active FE port outputs require the Task40 scoped schema")
    operator_scope = contract.get("operator_scope")
    parent_scope = contract.get("parent_inventory_scope")
    selection_policy = contract.get("selection_policy")
    full_dtn_status = contract.get("full_dtn_status")
    if not all(isinstance(value, str) and value.strip() for value in (
        operator_scope, parent_scope, selection_policy, full_dtn_status
    )):
        raise ValueError("active FE port output scope and inventory labels are required")
    if operator_scope == "A6_n0" or "n0" in operator_scope.lower():
        raise ValueError("Task40 active FE outputs cannot use the legacy N0 scope")
    if full_dtn_status != "FULL_DTN_NOT_VERIFIED":
        raise ValueError("finite active-port output cannot certify the full DtN operator")
    contract_cutoff_policy = contract.get("dtn_sparse_cutoff_policy")
    contract_cutoff_tolerance = contract.get(
        "dtn_sparse_cutoff_relative_tolerance"
    )
    contract_cutoff_identity = contract.get(
        "dtn_sparse_cutoff_identity_sha256"
    )
    expected_cutoff_tolerance = float(sparse_cutoff_relative_tolerance)
    if (
        contract_cutoff_policy != sparse_cutoff_policy
        or contract_cutoff_tolerance != expected_cutoff_tolerance
        or contract_cutoff_identity != sparse_cutoff_identity_sha256
        or not isinstance(contract_cutoff_identity, str)
        or not re.fullmatch(r"[0-9a-f]{64}", contract_cutoff_identity)
        or not np.isfinite(expected_cutoff_tolerance)
        or not 0.0 < expected_cutoff_tolerance < 1.0
    ):
        raise ValueError("active FE output cutoff identity differs from the live carrier")

    parent_count = contract.get("parent_mode_count")
    active_count = contract.get("active_mode_count")
    parent_sha = contract.get("parent_mode_sha256")
    active_sha = contract.get("active_mode_sha256")
    selected_sha = contract.get("selected_parent_indices_sha256")
    if (
        isinstance(parent_count, bool)
        or not isinstance(parent_count, int)
        or parent_count <= 0
        or isinstance(active_count, bool)
        or not isinstance(active_count, int)
        or active_count != int(active_mode_count)
        or active_count <= 0
        or active_count > parent_count
    ):
        raise ValueError("active FE port mode counts are inconsistent")
    if not isinstance(active_mode_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", active_mode_sha256):
        raise ValueError("live active FE port manifest SHA256 is invalid")
    for label, digest in (("parent", parent_sha), ("active", active_sha)):
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"{label} FE port manifest SHA256 is invalid")
    if active_sha != active_mode_sha256:
        raise ValueError("active FE output identity differs from the live DtN carrier")

    if active_count == parent_count:
        if parent_sha != active_sha or selected_sha is not None:
            raise ValueError("unfiltered active FE outputs must match the parent inventory")
        omitted = "NONE_WITHIN_DECLARED_PARENT"
    else:
        if parent_sha == active_sha:
            raise ValueError("truncated active FE output cannot alias the parent identity")
        if not isinstance(selected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", selected_sha):
            raise ValueError("truncated active FE output requires its parent-index identity")
        omitted = "NOT_COMPUTED"

    return {
        "output_scope": "ACTIVE_FE_DTN_PORTS",
        "operator_scope": operator_scope,
        "full_dtn_status": full_dtn_status,
        "parent_inventory_scope": parent_scope,
        "parent_mode_count": parent_count,
        "parent_mode_sha256": parent_sha,
        "active_mode_count": active_count,
        "active_mode_sha256": active_sha,
        "selection_policy": selection_policy,
        "selected_parent_indices_sha256": selected_sha,
        "dtn_sparse_cutoff_policy": contract_cutoff_policy,
        "dtn_sparse_cutoff_relative_tolerance": contract_cutoff_tolerance,
        "dtn_sparse_cutoff_identity_sha256": contract_cutoff_identity,
        "omitted_channel_values": omitted,
    }


def recover_p0_outputs(
    bundle: Mapping[str, Any], solution: Any, output_dir: Path, *,
    canonical_export: Any | None = None,
    export_all_port_modes: bool = False,
    active_port_outputs_only: bool = False,
    active_fe_port_output_contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recover E/H and compute the existing modal and diagnostic outputs.

    ``active_fe_port_output_contract`` is a separately named explicit policy
    for finite-element DtN carrier outputs. It does not reuse the historical
    ``active_port_outputs_only`` N0 contract and does not invoke sampled-field
    diffraction postprocessing.
    """

    from ..common.modes_3d import incident_power_3d
    from ..postprocessing.diffraction_3d import compute_diffraction_orders_3d
    from ..postprocessing.postprocess_3d import save_airbox_3d_fields
    from ..postprocessing.rta_3d import compute_volume_absorption_3d
    from .dtn_port_3d import _port_power_metrics

    if active_port_outputs_only and active_fe_port_output_contract is not None:
        raise ValueError("legacy N0 and active FE port output contracts are mutually exclusive")
    if active_fe_port_output_contract is not None and not export_all_port_modes:
        raise ValueError("active FE port outputs require exporting every active carrier mode")

    setup = bundle["setup"]
    floquet = setup["floquets"][6]
    field = restore_p0_full_field(floquet, solution, name="E_total")
    try:
        recovered_auxiliary = bundle["dtn_action"].recover_auxiliary(solution)
        aux = np.asarray(recovered_auxiliary, dtype=np.complex128)
        del recovered_auxiliary
        if not (len(bundle["modes"]) == len(bundle["incident_projections"]) == aux.size):
            raise ValueError("active FE port amplitudes do not match the live carrier mode list")
        active_output_identity = None
        if active_fe_port_output_contract is not None:
            active_output_identity = _active_fe_port_output_identity(
                active_fe_port_output_contract,
                active_mode_count=len(bundle["modes"]),
                active_mode_sha256=str(bundle.get("mode_sha256", "")),
                sparse_cutoff_policy=str(bundle["dtn_sparse_cutoff_policy"]),
                sparse_cutoff_relative_tolerance=float(
                    bundle["dtn_sparse_cutoff_relative_tolerance"]
                ),
                sparse_cutoff_identity_sha256=str(
                    bundle["dtn_sparse_cutoff_identity_sha256"]
                ),
            )
        port_metrics = _port_power_metrics(
            bundle["cfg"],
            list(bundle["modes"]),
            aux,
            list(bundle["incident_projections"]),
        )
        if active_port_outputs_only:
            # Preserve the original V7 N0 output contract verbatim.
            port_metrics.update(
                operator_scope="A6_n0", full_dtn_status="FULL_DTN_NOT_VERIFIED",
                parent_mode_count=32060, active_mode_count=572,
                omitted_channel_values="NOT_COMPUTED",
            )
        elif active_output_identity is not None:
            port_metrics.update(active_output_identity)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        canonical_facts = None if canonical_export is None else canonical_export(field, output_dir)
        if export_all_port_modes:
            from .dtn_port_3d import _write_port_outputs

            _write_port_outputs(output_dir, bundle['cfg'], list(bundle['modes']), aux,
                list(bundle['incident_projections']), port_metrics, setup['mesh_data'].mesh.comm)
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
        if active_port_outputs_only:
            if not export_all_port_modes or len(bundle["modes"]) != 572 or any(
                mode.n != 0 for mode in bundle["modes"]
            ):
                raise ValueError("active-only output requires the complete 572-mode N0 carrier")
            diffraction_metrics = {
                "status": "N0_ACTIVE_PORT_OUTPUT",
                "diffraction_channel_count": len(bundle["modes"]),
                "operator_scope": "A6_n0",
                "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
                "omitted_channel_values": "NOT_COMPUTED",
                "source": "dtn_port_diffraction_orders_3d.json",
            }
        elif active_output_identity is not None:
            diffraction_metrics = {
                "status": "ACTIVE_FE_PORT_OUTPUT",
                "diffraction_channel_count": len(bundle["modes"]),
                **active_output_identity,
                "source": "dtn_port_diffraction_orders_3d.json",
                "sampling_dft_used": False,
            }
        else:
            diffraction_metrics = compute_diffraction_orders_3d(
                setup["mesh_data"], bundle["cfg"], field, output_dir
            )
        facts = {
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
        if canonical_export is not None:
            facts['canonical_vector'] = canonical_facts
        return facts
    finally:
        del field


def restore_p0_full_field(floquet: Any, solution: Any, *, name: str = "E_total") -> Any:
    """Recreate the full primal field from the saved zero-slave storage vector.

    The scatter/homogenize/backsubstitute/scatter sequence is shared by the
    production P0 output path and the offline R13 pair checker.
    """

    from dolfinx import fem

    field = fem.Function(floquet.mpc.function_space, name=name)
    if isinstance(solution, np.ndarray):
        if solution.shape != field.x.array.shape:
            raise ValueError("saved retained vector differs from the P0 function-space storage")
        field.x.array[:] = solution
    else:
        solution.copy(field.x.petsc_vec)
    field.x.scatter_forward()
    floquet.mpc.homogenize(field)
    field.x.scatter_forward()
    floquet.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


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
    coarse_solver = setup.pop("owned_coarse_solver", None)
    if coarse_solver is not None:
        coarse_solver.destroy()
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
    "build_same_mesh_physical_action",
    "build_p6_same_mesh_physical_bundle",
    "build_physical_rhs",
    "destroy_p6_same_mesh_physical_bundle",
    "destroy_same_mesh_physical_action",
    "release_p6_same_mesh_solver_stack",
    "recover_p0_outputs",
)
