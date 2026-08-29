"""Minimal same-cache form precompile groups for the selected p6 profile.

Each call builds the real same-mesh ingredients needed by one group, compiles
only the requested UFL forms, and returns facts rather than FE or PETSc
objects.  The caller owns the process-level cache and no solver object is
constructed here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


JIT_GROUPS = (
    "positive-p6",
    "positive-p3",
    "positive-p1",
    "dtn-surface",
    "incident-rhs",
    "physical-volume",
)
JIT_GROUP_SCHEMA = "task038.same-mesh-hcurl-pmg.jit-precompile.v1"


def _form_kwargs(
    jit_options: Mapping[str, Any],
    quadrature_degree: int | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"jit_options": dict(jit_options)}
    if quadrature_degree is not None:
        kwargs["form_compiler_options"] = {
            "quadrature_degree": int(quadrature_degree)
        }
    return kwargs


def _compile_form(
    form: Any,
    jit_options: Mapping[str, Any],
    quadrature_degree: int | None = None,
) -> Any:
    from dolfinx import fem

    return fem.form(form, **_form_kwargs(jit_options, quadrature_degree))


def _facts(
    group: str,
    degree: int,
    forms: list[dict[str, Any]],
    jit_options: Mapping[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schema": JIT_GROUP_SCHEMA,
        "group": group,
        "degree": int(degree),
        "compiled_form_count": len(forms),
        "form_roles": [str(item["role"]) for item in forms],
        "forms": forms,
        "jit_options": dict(jit_options),
        "same_physical_mesh": True,
        "objects": {
            "fullspace_mpc_form_action": False,
            "same_mesh_p6_shell": False,
            "constrained_diagonal": False,
            "assembled_matrix": False,
            "p3_matrix": False,
            "p1_matrix": False,
            "surface_entries": False,
            "dtn_carrier": False,
            "dtn_action": False,
            "rhs_vector": False,
            "physical_ksp": False,
            "pc": False,
            "factor": False,
            "solve": False,
            "recovery": False,
        },
        **extra,
    }


def _levels(
    cfg: Any,
    comm: Any,
    degree: int,
    *,
    include_positive_coefficients: bool = True,
) -> tuple[dict[str, Any], Any]:
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels

    levels = _build_same_mesh_levels(
        cfg,
        comm,
        (int(degree),),
        include_positive_coefficients=include_positive_coefficients,
    )
    return levels, levels["spaces"][int(degree)]


def _mode_facts(cfg: Any) -> tuple[int, str, int]:
    from .dtn_port_3d import _dtn_surface_quadrature_degree
    from .fullspace_dtn_action import build_dynamic_mode_inventory

    modes, _rows, mode_sha = build_dynamic_mode_inventory(cfg)
    qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
    return int(len(modes)), str(mode_sha), int(qdegree)


def _build_positive_p6(
    cfg: Any, comm: Any, jit_options: Mapping[str, Any]
) -> dict[str, Any]:
    import ufl
    from dolfinx import fem

    from .fullspace_same_mesh_hcurl_pmg_global import same_mesh_positive_form

    levels, space = _levels(
        cfg, comm, 6, include_positive_coefficients=True
    )
    form = same_mesh_positive_form(
        space,
        curl_coefficient=levels["mu"],
        mass_coefficient=levels["mass"],
    )
    coefficient = fem.Function(space)
    action = ufl.action(form, coefficient)
    _compile_form(action, jit_options)
    _compile_form(form, jit_options)
    del action, coefficient, form, levels
    return _facts(
        "positive-p6",
        6,
        [
            {"role": "positive_p6_action", "rank": 1, "kind": "action"},
            {"role": "positive_p6_bilinear", "rank": 2, "kind": "bilinear"},
        ],
        jit_options,
    )


def _build_positive_coarse(
    cfg: Any, comm: Any, degree: int, jit_options: Mapping[str, Any]
) -> dict[str, Any]:
    from .fullspace_same_mesh_hcurl_pmg_global import same_mesh_positive_form

    levels, space = _levels(
        cfg, comm, degree, include_positive_coefficients=True
    )
    form = same_mesh_positive_form(
        space,
        curl_coefficient=levels["mu"],
        mass_coefficient=levels["mass"],
    )
    _compile_form(form, jit_options)
    del form, levels
    return _facts(
        f"positive-p{int(degree)}",
        degree,
        [
            {
                "role": f"positive_p{int(degree)}_bilinear",
                "rank": 2,
                "kind": "bilinear",
            }
        ],
        jit_options,
    )


def _build_dtn_surface(
    cfg: Any, comm: Any, jit_options: Mapping[str, Any]
) -> dict[str, Any]:
    from .fullspace_same_mesh_hcurl_pmg_physical import _surface_assemblers

    levels, space = _levels(
        cfg, comm, 6, include_positive_coefficients=False
    )
    mode_count, mode_sha, qdegree = _mode_facts(cfg)
    assemblers = _surface_assemblers(
        space,
        levels["mesh_data"],
        cfg,
        qdegree,
        jit_options=jit_options,
    )
    roles = [
        {
            "role": f"dtn_surface_{side}_{component}",
            "rank": 1,
            "kind": "surface_linear",
        }
        for side in ("top", "bottom")
        for component in (0, 1)
    ]
    del assemblers, levels
    return _facts(
        "dtn-surface",
        6,
        roles,
        jit_options,
        mode_count=mode_count,
        mode_manifest_sha256=mode_sha,
        dtn_quadrature_degree=qdegree,
    )


def _build_incident_rhs(
    cfg: Any, comm: Any, jit_options: Mapping[str, Any]
) -> dict[str, Any]:
    from .dtn_port_3d import _incident_top_traction_form

    levels, space = _levels(
        cfg, comm, 6, include_positive_coefficients=False
    )
    mode_count, mode_sha, qdegree = _mode_facts(cfg)
    form = _incident_top_traction_form(space, levels["mesh_data"], cfg)
    _compile_form(form, jit_options, qdegree)
    del form, levels
    return _facts(
        "incident-rhs",
        6,
        [{"role": "incident_top_traction", "rank": 1, "kind": "linear"}],
        jit_options,
        mode_count=mode_count,
        mode_manifest_sha256=mode_sha,
        dtn_quadrature_degree=qdegree,
    )


def _build_physical_volume(
    cfg: Any, comm: Any, jit_options: Mapping[str, Any]
) -> dict[str, Any]:
    import ufl
    from dolfinx import fem

    from .common_3d_forms import _build_variational_forms

    levels, space = _levels(
        cfg, comm, 6, include_positive_coefficients=False
    )
    bilinear, rhs_form = _build_variational_forms(
        levels["mesh"],
        levels["mesh_data"],
        cfg,
        space,
        field_formulation="total_field",
    )
    coefficient = fem.Function(space)
    action = ufl.action(bilinear, coefficient)
    _compile_form(action, jit_options)
    del action, coefficient, bilinear, rhs_form, levels
    return _facts(
        "physical-volume",
        6,
        [{"role": "physical_volume_action", "rank": 1, "kind": "action"}],
        jit_options,
    )


def build_minimal_jit_group(
    cfg: Any, comm: Any, group: str
) -> dict[str, Any]:
    """Compile one fixed group using the selected same-mesh construction."""

    from .fullspace_same_mesh_hcurl_pmg_setup import (
        SAME_MESH_JIT_OPTIONS,
        validate_p6_setup_config,
    )

    if group not in JIT_GROUPS:
        raise ValueError(f"unsupported JIT precompile group: {group!r}")
    validate_p6_setup_config(cfg)
    if int(comm.size) != 1:
        raise ValueError("JIT precompile is fixed to MPI1")
    jit_options = SAME_MESH_JIT_OPTIONS
    if group == "positive-p6":
        return _build_positive_p6(cfg, comm, jit_options)
    if group == "positive-p3":
        return _build_positive_coarse(cfg, comm, 3, jit_options)
    if group == "positive-p1":
        return _build_positive_coarse(cfg, comm, 1, jit_options)
    if group == "dtn-surface":
        return _build_dtn_surface(cfg, comm, jit_options)
    if group == "incident-rhs":
        return _build_incident_rhs(cfg, comm, jit_options)
    return _build_physical_volume(cfg, comm, jit_options)


__all__ = ("JIT_GROUPS", "JIT_GROUP_SCHEMA", "build_minimal_jit_group")
