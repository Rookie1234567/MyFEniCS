from __future__ import annotations

import os
from time import perf_counter

import numpy as np
import pytest
import ufl
from dolfinx import fem, mesh
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity.profile import task43_initial_profile
from src.adaptivity.variable_p_degree_plan import (
    build_variable_p_cell_degree_plan,
    cell_box_catalog,
)
from src.solvers.common_3d_forms import _build_physical_volume_terms
from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _tabulate_raw_tensor_class,
)
from src.solvers.hcurl_blocked_gram_tensor import HcurlBlockedGramTensor
from src.solvers.hcurl_variable_p_assembly import (
    build_variable_p_condensed_trace_system_from_compiled_form,
)


def _task43_p6_component_case():
    comm = MPI.COMM_WORLD
    if comm.size != 1:
        pytest.skip("one-cell p6 qualification is serial-only")
    cfg = task43_initial_profile()
    cfg.nedelec_degree = 6
    domain = mesh.create_unit_cube(
        comm,
        1,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    cell_tags = mesh.meshtags(
        domain,
        domain.topology.dim,
        np.asarray([0], dtype=np.int32),
        np.asarray([cfg.tags.air], dtype=np.int32),
    )
    space = fem.functionspace(domain, ("N1curl", 6))
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    dx = ufl.Measure(
        "dx",
        domain=domain,
        subdomain_data=cell_tags,
        metadata={
            "quadrature_degree": cfg.stage4_volume_quadrature_degree,
            "quadrature_rule": cfg.stage4_volume_quadrature_rule,
        },
    )
    curl_form, mass_form = _build_physical_volume_terms(
        cfg,
        trial,
        test,
        dx,
    )
    bilinear_form = curl_form + mass_form
    stage_started = perf_counter()
    compiled = fem.form(bilinear_form)
    print(
        f"TASK43_P6_STAGE form_compiled_seconds={perf_counter() - stage_started:.6f}",
        flush=True,
    )
    kernels = _cell_integral_kernels(
        compiled,
        sum_duplicate_cell_integrals=True,
    )
    stage_started = perf_counter()
    blocked = HcurlBlockedGramTensor(
        space.element.basix_element,
        cfg,
        bilinear_form,
        compiled_form=compiled,
    )
    print(
        f"TASK43_P6_STAGE blocked_gram_bound_seconds={perf_counter() - stage_started:.6f}",
        flush=True,
    )
    coordinates, _widths = _canonical_axis_aligned_coordinates(
        domain,
        0,
        tolerance=1.0e-12,
        geometry_identity_policy="raw_unrounded",
    )
    return cfg, domain, cell_tags, space, compiled, kernels, blocked, coordinates


@pytest.mark.skipif(
    os.environ.get("TASK43_RUN_P6_FFCX_MATRIX_WITNESS") != "1",
    reason="full p6 FFCx matrix witness is an explicit timed component test",
)
def test_task43_p6_carrier_grating_gram_matches_ffcx() -> None:
    cfg, _domain, _cell_tags, space, compiled, kernels, blocked, coordinates = (
        _task43_p6_component_case()
    )
    dimension = int(space.element.basix_element.dim)
    started = perf_counter()
    print("TASK43_P6_STAGE grating_ffcx_tensor_started", flush=True)
    ffcx = _tabulate_raw_tensor_class(
        compiled,
        kernels,
        coordinates,
        tag=int(cfg.tags.grating),
        dimension=dimension,
    )
    ffcx_seconds = perf_counter() - started
    print(
        f"TASK43_P6_STAGE grating_ffcx_tensor_seconds={ffcx_seconds:.6f}",
        flush=True,
    )
    started = perf_counter()
    candidate = blocked(
        compiled,
        kernels,
        coordinates,
        tag=int(cfg.tags.grating),
        dimension=dimension,
    )
    candidate_seconds = perf_counter() - started
    scale = max(float(np.linalg.norm(ffcx)), np.finfo(float).tiny)
    relative = float(np.linalg.norm(candidate - ffcx) / scale)
    print(
        "TASK43_P6_STAGE grating_blocked_gram_seconds="
        f"{candidate_seconds:.6f} relative={relative:.17e}",
        flush=True,
    )
    assert relative <= 1.0e-10
    audit = blocked.audit()
    assert audit["element_degree"] == 6
    assert audit["ffcx_default_kernel_absent"] is True
    assert all(
        record["degree"] == cfg.stage4_volume_quadrature_degree
        and record["rule"] == cfg.stage4_volume_quadrature_rule
        for record in audit["integral_rule_records"]
    )


def test_task43_p6_carrier_blocked_gram_builds_active_p3() -> None:
    (
        _cfg,
        domain,
        cell_tags,
        space,
        compiled,
        _kernels,
        blocked,
        _coordinates,
    ) = _task43_p6_component_case()
    degree_plan = build_variable_p_cell_degree_plan(
        domain,
        {box: 3 for box in cell_box_catalog(domain)},
    )
    assert all(
        np.all(degrees == 3)
        for degrees in degree_plan.entity_map.global_degrees.values()
    )
    started = perf_counter()
    system = build_variable_p_condensed_trace_system_from_compiled_form(
        compiled,
        space,
        cell_tags,
        degree_plan.entity_map,
        raw_tensor_evaluator=blocked,
    )
    print(
        f"TASK43_P6_STAGE active_p3_builder_seconds={perf_counter() - started:.6f}",
        flush=True,
    )
    try:
        evaluator_audit = system.build_audit["raw_tensor_evaluator"]
        assert (
            evaluator_audit["implementation"]
            == "hcurl_isotropic_blocked_gram_ffcx_rules_v1"
        )
        assert evaluator_audit["element_degree"] == 6
        assert evaluator_audit["ffcx_default_kernel_absent"] is True
        assert system.build_audit["raw_tensor_class_count_global_unique"] == 1
    finally:
        system.destroy()
