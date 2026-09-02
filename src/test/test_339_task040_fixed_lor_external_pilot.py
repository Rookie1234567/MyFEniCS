"""Focused route and one-cell preconditioner-only pilot contract."""

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI

from benchmarks.task040_level_a import (
    V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_FLAG,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_SCHEMA,
    V9_E_LOR_BARE_F_EXTERNAL_ONLY_TIMEOUT_SECONDS,
    V9_E_LOR_L2_ONLY_FLAG,
    build_task040_level_a_plan,
    run_task040_level_a,
)
from benchmarks.task040_level_a_watchdog import build_task040_level_a_watchdog_plan
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hcurl_fixed_lor_cell_bridge import (
    build_fixed_p6_lor_cell_bridge,
)
from src.solvers.hcurl_fixed_lor_trace_service import build_fixed_lor_trace_service

ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_INPUT = ROOT / V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT
EXTERNAL_FLAG = V9_E_LOR_BARE_F_EXTERNAL_ONLY_FLAG


def _route_kwargs(tmp_path):
    return {
        "input_path": OFFICIAL_INPUT,
        "exact_spool_root": tmp_path / "unused-spool",
        "run_directory": tmp_path / "fresh-run",
        "source_sha": "a" * 40,
        "v9_e_lor_bare_f_external_only": True,
    }


def test_task040_external_plan_and_watchdog_contract(tmp_path):
    kwargs = _route_kwargs(tmp_path)
    plan = build_task040_level_a_plan(**kwargs)
    assert plan["method"] == V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD
    assert plan["schema"] == V9_E_LOR_BARE_F_EXTERNAL_ONLY_SCHEMA
    assert plan["input"] == str(OFFICIAL_INPUT)
    assert plan["mpi_size"] == 8
    assert plan["threads"] == 1
    assert plan["watchdog_required"] is True
    assert plan["bottom_route_only_required"] is True
    assert (
        plan["timeout_seconds"] == V9_E_LOR_BARE_F_EXTERNAL_ONLY_TIMEOUT_SECONDS
    )
    assert plan["watchdog_hard_stop_bytes"] == (
        V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES
    )
    assert plan["swap_limit_bytes"] == 0
    fixed = plan["fixed_configuration"]
    assert fixed["bottom_operator"] == "physical_current_bare_f_matshell"
    assert fixed["pc_operator"] == "fixed_positive_lor_trace_preconditioner"
    assert fixed["pc_binding"] == "preconditioner_only"
    assert fixed["pc_curl_coefficient"] == [1.0, 0.0]
    assert fixed["pc_mass_coefficient"] == [1.0, 0.0]
    assert fixed["source_only"] == "external_dtn_coupling"
    assert fixed["physical_dtn_used"] is False
    assert fixed["additional_absorbing_shift"] == 0.0
    assert fixed["fgmres"] == {
        "type": "right_fgmres",
        "restart": 64,
        "max_it": 256,
        "rtol": 1.0e-8,
        "atol": 0.0,
        "explicit_residual_gate": 1.0e-3,
        "general_record_gate": 1.0e-2,
    }
    assert plan["global_F"] is False
    assert plan["global_AIJ"] is False
    assert plan["global_factor"] is False
    assert plan["factor_inventory"]["owner_local_bounded"] is True
    assert plan["factor_inventory"]["max_local_rows"] == 432
    assert plan["factor_inventory"]["max_local_rows_limit"] == 1024
    assert plan["factor_inventory"]["global_direct_factor_count"] == 0
    assert plan["factor_inventory"]["global_coarse_factor_count"] == 0
    assert plan["factor_inventory"]["global_full_side_factor_count"] == 0
    assert plan["factor_inventory"]["global_full_cross_factor_count"] == 0
    assert {
        "physical_dtn_matrix",
        "global_high_order_aij",
        "global_factor",
        "global_coarse_factor",
        "full_cross_section_factor",
        "parameter_scan",
        "five_source",
        "retry",
        "top",
        "hybrid",
        "official_rta",
    }.issubset(set(plan["forbidden"]))

    watchdog = build_task040_level_a_watchdog_plan(**kwargs)
    assert watchdog["method"] == V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD
    assert watchdog["mpi_size"] == 8
    assert watchdog["threads"] == 1
    watched = watchdog["watchdog"]
    assert (
        watched["hard_stop_bytes"]
        == V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES
    )
    assert watched["swap_limit_bytes"] == 0
    assert (
        watched["timeout_seconds"]
        == V9_E_LOR_BARE_F_EXTERNAL_ONLY_TIMEOUT_SECONDS
    )
    assert (
        watched["cleanup_stage"] == V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[-1]
    )
    assert watched["marker_sequence"] == list(
        V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE
    )
    assert watchdog["worker_argv"].count(EXTERNAL_FLAG) == 1
    assert V9_E_LOR_L2_ONLY_FLAG not in watchdog["worker_argv"]

    h5 = ROOT / "input/official/task039/5nm_p6h5_full3d_direct_mpi8.dat"
    with pytest.raises(ValueError):
        build_task040_level_a_plan(**(kwargs | {"input_path": h5}))
    with pytest.raises(ValueError):
        build_task040_level_a_plan(**(kwargs | {"v9_e_lor_l2_only": True}))


def test_task040_external_authority_preflight_contract():
    import benchmarks.task040_level_a as level_a

    kwargs = {
        "comm": SimpleNamespace(size=8, rank=0),
        "input_path": OFFICIAL_INPUT,
        "input_sha256": (
            "e8b60ba70daa2074c21603d463790a28c881d35d7bd17b2b8315fef0318007b6"
        ),
        "physical_model_sha256": (
            "db52c70d667caa726e2b2e04b646402415a377fa7bbcef42c87ffc816b9b2a7a"
        ),
        "source_sha": "c" * 40,
        "watchdog_enabled": True,
        "bottom_route_only": True,
    }
    result = level_a._v9_e_lor_bare_f_external_authority_preflight(**kwargs)
    assert result["pass"] is True
    assert result["observed"]["resolved_config_sha256"] == (
        "a35bb4e35088a33ecd59161bf41307c092cae4a11dba30e8336026833bc40c3e"
    )
    assert result["external_mode_authority"]["full_count"] == 604
    assert result["external_mode_authority"]["bottom_count"] == 300
    mismatch = level_a._v9_e_lor_bare_f_external_authority_preflight(
        **(kwargs | {"input_sha256": "0" * 64})
    )
    assert mismatch["pass"] is False
    assert "input_sha256" in mismatch["failures"]
    assert mismatch["external_mode_authority"] is None


def test_task040_external_identity_preflight_binding(monkeypatch, tmp_path):
    import benchmarks.task040_level_a as level_a
    import src.solvers.hybrid_bare_f_external_lor_pilot as pilot

    comm = SimpleNamespace(size=8, rank=0)
    authority = {"sentinel": "external-mode-authority"}
    resolved_sha = "d" * 64
    preflight_calls = []
    pilot_calls = []

    def fake_preflight(**kwargs):
        preflight_calls.append(kwargs)
        return {
            "pass": len(preflight_calls) == 1,
            "failures": [] if len(preflight_calls) == 1 else ["identity"],
            "external_mode_authority": authority,
            "observed": {"resolved_config_sha256": resolved_sha},
        }

    def fake_pilot(**kwargs):
        pilot_calls.append(kwargs)
        return {"status": "sentinel"}

    monkeypatch.setattr(
        level_a,
        "_v9_e_lor_bare_f_external_authority_preflight",
        fake_preflight,
    )
    monkeypatch.setattr(
        pilot, "run_v9_e_lor_bare_f_external_only", fake_pilot
    )
    common = {
        "cfg": object(),
        "profile": object(),
        "comm": comm,
        "exact_spool_root": tmp_path / "spool",
        "source_sha": "c" * 40,
        "input_path": OFFICIAL_INPUT,
        "input_sha256": "a" * 64,
        "physical_model_sha256": "b" * 64,
        "marker_callback": None,
        "resource_callback": dict,
        "watchdog_enabled": True,
        "bottom_route_only": True,
        "watchdog_hard_stop_bytes": V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES,
        "v9_e_lor_bare_f_external_only": True,
    }
    result = run_task040_level_a(
        run_directory=tmp_path / "first", **common
    )
    assert result == {"status": "sentinel"}
    assert preflight_calls[0]["comm"] is comm
    assert preflight_calls[0]["input_path"] == OFFICIAL_INPUT
    assert preflight_calls[0]["input_sha256"] == "a" * 64
    assert preflight_calls[0]["physical_model_sha256"] == "b" * 64
    assert preflight_calls[0]["source_sha"] == "c" * 40
    assert preflight_calls[0]["watchdog_enabled"] is True
    assert preflight_calls[0]["bottom_route_only"] is True
    assert pilot_calls[0]["external_mode_authority"] is authority
    assert pilot_calls[0]["external_mode_current_resolved_config_sha256"] == (
        resolved_sha
    )

    result = run_task040_level_a(
        run_directory=tmp_path / "failed", **common
    )
    assert result["status"] == "V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE"
    assert result["preflight_failures"] == ["identity"]
    assert len(pilot_calls) == 1


@pytest.fixture(scope="module")
def external_lor_fixture():
    comm = MPI.COMM_WORLD
    domain = mesh.create_box(
        comm,
        [np.array([0.0, 0.0, 0.0]), np.array([1.0, 1.0, 1.0])],
        [1, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    tdim = domain.topology.dim
    domain.topology.create_entity_permutations()
    local_cells = domain.topology.index_map(tdim).size_local
    cell_ids = np.arange(local_cells, dtype=np.int32)
    cell_tags = mesh.meshtags(
        domain,
        tdim,
        cell_ids,
        np.full(local_cells, 7, dtype=np.int32),
    )
    V = fem.functionspace(
        domain,
        element("N1curl", domain.basix_cell(), 6, dtype=default_real_type),
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=domain, subdomain_data=cell_tags)
    form = fem.form(
        (ufl.inner(ufl.curl(u), ufl.curl(v)) + 2.0 * ufl.inner(u, v)) * dx(7)
    )
    condensed = build_unconstrained_assembly_time_condensation(
        form,
        V,
        cell_tags,
        materialize_global_matrix=False,
        retain_local_schur_for_matrix_free=True,
    )
    bridges = {}
    retained = condensed.retained_local_schur_by_class
    if retained is None:
        raise RuntimeError("the action-only fixture did not retain local Schur data")
    for class_key in retained:
        _tag, wx, wy, wz, cell_info = class_key
        bridges[class_key] = build_fixed_p6_lor_cell_bridge(
            widths=(float(wx), float(wy), float(wz)),
            curl_coefficient=1.0 + 0.0j,
            mass_coefficient=1.0 + 0.0j,
            cell_info=int(cell_info),
        )
    service = build_fixed_lor_trace_service(
        condensed,
        bridges,
        operator_binding="preconditioner_only",
    )
    try:
        yield {
            "comm": comm,
            "domain": domain,
            "condensed": condensed,
            "bridges": bridges,
            "service": service,
        }
    finally:
        service.destroy()
        for bridge in bridges.values():
            bridge.destroy()
        condensed.destroy()


def _relative(first, second):
    difference = first.duplicate()
    first.copy(difference)
    difference.axpy(-1.0, second)
    denominator = max(float(first.norm()), float(second.norm()), 1.0e-300)
    value = float(difference.norm()) / denominator
    difference.destroy()
    return value


def _fill(vector):
    start, end = vector.getOwnershipRange()
    rows = np.arange(start, end, dtype=np.float64)
    values = (0.25 + 0.01 * rows) + 1j * (0.5 - 0.002 * rows)
    vector.getArray()[:] = values
    vector.assemble()


def test_task040_external_preconditioner_fixture_contract(external_lor_fixture):
    fixture = external_lor_fixture
    comm = fixture["comm"]
    service = fixture["service"]
    audit = service.audit
    tags = [int(key[0]) for key in fixture["bridges"]]
    assert any(value != 1 for values in comm.allgather(tags) for value in values)
    with pytest.raises(ValueError):
        build_fixed_lor_trace_service(
            fixture["condensed"], fixture["bridges"], operator_binding="invalid"
        )
    assert audit["pass"] is True
    assert audit["operator_binding"] == "preconditioner_only"
    assert audit["production_bridge_identity_required"] is False
    assert audit["production_bridge_identity_applied"] is False
    assert audit["production_bridge_identity_passed"] is None
    assert audit["production_bridge_comparison_computed"] is True
    assert audit["prod_vs_bridge_max_relative"] > 1.0e-10
    assert audit["hermitian_max_relative"] <= 1.0e-10
    assert audit["factor_solve_relative_max"] <= 1.0e-10
    assert audit["coverage_global_min"] > 0.0
    assert audit["max_local_factor_rows"] <= 432
    assert audit["numeric_allgather"] is False
    assert audit["full_basis_replication"] is False
    local_factor_bytes = audit["retained_numpy_factor_map_bytes_not_peak"]
    assert local_factor_bytes >= 0
    assert comm.allreduce(local_factor_bytes, op=MPI.SUM) > 0
    assert audit["retained_work_vector_payload_bytes_not_peak"] >= 0
    assert audit["destroyed"] is False

    source = fixture["condensed"].create_active_vector()
    target = source.duplicate()
    repeated = source.duplicate()
    try:
        _fill(source)
        service.apply(None, source, target)
        service.apply(None, source, repeated)
        assert _relative(target, repeated) <= 1.0e-10
        assert service.audit["apply_count"] == 2
        assert service.audit["solve_count"] == 0
    finally:
        source.destroy()
        target.destroy()
        repeated.destroy()
    service.destroy()
    assert service.destroyed is True
    with pytest.raises(RuntimeError):
        service.apply(None, source, target)


def test_task040_external_cleanup_marker_on_assembly_failure(monkeypatch, tmp_path):
    import src.solvers.hybrid_bare_f_external_lor_pilot as pilot

    markers = []
    authority = {
        "authority_file_path": "authority.json",
        "authority_file_sha256": "a" * 64,
        "inventory_canonical_sha256": "b" * 64,
        "source_path": V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT,
        "full_count": 604,
        "bottom_count": 300,
        "canonical_key_list_sha256": "c" * 64,
        "resolved_mode_metadata_sha256": "d" * 64,
        "legacy_beta_metadata_sha256": "e" * 64,
        "legacy_beta_metadata_schema": "canonical_json_bottom_beta_pairs",
        "resolved_config_sha256": "f" * 64,
    }

    def capture(stage, _callback, _comm, _started, _resource, **detail):
        markers.append((stage, detail))

    def fail_at_assembly(*_args, **_kwargs):
        raise RuntimeError("sentinel assembly failure")

    monkeypatch.setattr(pilot, "_marker", capture)
    monkeypatch.setattr(
        pilot, "assemble_current_bare_f_authority_system", fail_at_assembly
    )
    with pytest.raises(RuntimeError, match="sentinel assembly failure"):
        pilot.run_v9_e_lor_bare_f_external_only(
            cfg=object(),
            profile=SimpleNamespace(bottom_interface_nm=0.0, top_interface_nm=1.0),
            comm=SimpleNamespace(size=8, rank=0),
            input_path=OFFICIAL_INPUT,
            run_directory=tmp_path / "cleanup-marker",
            source_sha="a" * 40,
            input_sha256=(
                "e8b60ba70daa2074c21603d463790a28c881d35d7bd17b2b8315fef0318007b6"
            ),
            physical_model_sha256="b" * 64,
            external_mode_authority=authority,
            external_mode_current_resolved_config_sha256="f" * 64,
            marker_callback=None,
            resource_callback=dict,
            watchdog_enabled=True,
            bottom_route_only=True,
            watchdog_hard_stop_bytes=V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES,
        )
    cleanup_stage, detail = markers[-1]
    assert cleanup_stage == pilot.V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[-1]
    assert detail["status"] == "complete"
    assert detail["classification"] == (
        pilot.V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE
    )
