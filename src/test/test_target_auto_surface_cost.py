"""Pure config/NumPy/AST tests. Original AUTO and all FE operations stay unrun."""
import ast
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

SOURCE = Path(__file__).resolve().parents[1] / "solvers" / "target_auto_surface_cost.py"
spec = importlib.util.spec_from_file_location("target_auto_surface_cost", SOURCE)
candidate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = candidate
spec.loader.exec_module(candidate)


def fake_mode(m, n, *, polarization="s", side="top", beta=1, cutoff=False, propagating=True):
    return SimpleNamespace(m=m, n=n, polarization=polarization, side=side, beta=complex(beta),
                           rayleigh_warning=cutoff, propagating=propagating,
                           k_vector=(1+0j, 0j, complex(beta) if side == "top" else -complex(beta)))


def test_explicit_physical_configuration_and_planes():
    cfg = candidate.target_config()
    assert (cfg.lambda0, cfg.period_x, cfg.period_y, cfg.z_min, cfg.z_max, cfg.interface_z) == (0.7, 50, 25, -10, 130, 0)
    assert (cfg.grating_width_x, cfg.grating_width_y, cfg.grating_height) == (17, 25, 120)
    assert cfg.n_substrate == cfg.n_grating == complex(0.99988517036884961, 4.3236152269189515e-06)
    assert cfg.n_air == cfg.mu_r == cfg.incident_amplitude == 1+0j
    assert (cfg.incident_theta_deg, cfg.incident_phi_deg, cfg.polarization_kind) == (89, 0, "s")
    assert cfg.custom_polarization is None and not cfg.use_pml
    assert cfg.cell_notch is None and cfg.air_void_box_nm is None
    assert cfg.geometry_model_variant == "original"
    assert cfg.mesh_axis_z_profile == "exact_planes_18cell_boundary_compiler_fixture"
    assert cfg.nedelec_degree == 6 and cfg.nedelec_trace_degree is None and cfg.nedelec_interior_degree is None
    assert cfg.stage4_dtn_order_policy == "auto_propagating"
    assert cfg.diffraction_order_max_m is None and cfg.diffraction_order_max_n is None
    assert not cfg.diffraction_zero_order_only
    assert tuple(map(len, candidate.AXES)) == (4, 3, 4)
    assert np.prod([len(a)-1 for a in candidate.AXES]) == 18
    assert cfg.mesh_axis_x_values == (0, 16.5, 33.5, 50)
    assert cfg.mesh_axis_y_values == (0, 12.5, 25)
    assert cfg.mesh_axis_z_values == (-10, 0, 120, 130)
    snapshot = cfg.as_jsonable()
    assert candidate.sha256(candidate.canonical(snapshot)) == candidate.sha256(candidate.canonical(cfg.as_jsonable()))


def test_actual_production_pure_axis_geometry_and_constraint_guards():
    # Qualified FE imports are allowed; these original helpers execute only
    # config/axis arithmetic and never create a mesh, form, space or constraint.
    from src.geometry.mesh_builder_3d import _stage4_axis_plan, _validate_stage4_hexa_geometry
    from src.constraints.floquet_3d import _resolve_constraint_mode
    cfg = candidate.target_config()
    _validate_stage4_hexa_geometry(cfg)
    plan = _stage4_axis_plan(cfg, 1)
    assert plan.mesh_cells_resolved == (3, 2, 3)
    assert plan.material_plane_alignment["all_aligned"] is True
    for actual, expected in zip((plan.x_values, plan.y_values, plan.z_values), candidate.AXES):
        assert np.array_equal(actual, np.asarray(expected))
    assert _resolve_constraint_mode(None, cfg) == "topological_trace_p6"
    assert cfg.box_lengths == (50, 25, 140)
    assert (cfg.grating_x_min, cfg.grating_x_max, cfg.grating_y_min, cfg.grating_y_max,
            cfg.grating_z_min, cfg.grating_z_max) == (16.5, 33.5, 0, 25, 0, 120)


def test_four_tuple_selection_preserves_original_indices_and_both_polarizations():
    modes = [fake_mode(0, 0, side="bottom")]
    for m, n, beta in [(0, 0, 10), (-9, 1, 4), (2, -7, 5), (1, 1, 0.0001), (3, 2, 3)]:
        modes.extend(fake_mode(m, n, beta=beta, polarization=p) for p in ("s", "p"))
    indices, reasons = candidate.select_top_modes(modes)
    assert indices == tuple(range(1, 9))
    assert len(reasons) == 4
    assert {tuple(r["tuple"]) for r in reasons} == {(0, 0), (-9, 1), (2, -7), (1, 1)}
    small = next(r for r in reasons if "smallest_abs_beta" in r["reasons"])
    assert small["actual_near_cutoff"] is False
    assert all(candidate.mode_key(i, modes[i])[0] == i for i in indices)


def test_selection_deduplicates_tuple_reasons_and_tracks_actual_cutoff():
    modes = [fake_mode(0, 0, cutoff=True, polarization=p) for p in ("s", "p")]
    indices, reasons = candidate.select_top_modes(modes)
    assert indices == (0, 1) and len(reasons) == 1
    assert len(reasons[0]["reasons"]) == 4 and reasons[0]["actual_near_cutoff"] is True


def test_selection_rejects_missing_incident_or_more_than_two_polarizations():
    with pytest.raises(ValueError, match="incident"):
        candidate.select_top_modes([fake_mode(1, 1)])
    with pytest.raises(ValueError, match="bound"):
        candidate.select_top_modes([fake_mode(0, 0, polarization=p) for p in ("s", "p", "third")])


def test_phase_log_bounds_do_not_evaluate_exponentials(monkeypatch):
    monkeypatch.setattr(np, "exp", lambda *_args, **_kwargs: pytest.fail("global exponential evaluated"))
    modes = [fake_mode(0, 0, beta=2+3j), fake_mode(1, 0, beta=5+7j, cutoff=True),
             fake_mode(0, 0, side="bottom", beta=1+4j, propagating=False)]
    summary = candidate.inventory_summary(candidate.target_config(), modes)
    assert summary["fresh_mode_count"] == 3
    assert summary["classification_counts"]["top"] == {"propagating": 1, "evanescent": 0, "near-cutoff": 1}
    assert summary["boundary_phase_bounds"]["top"]["global_z_log_abs_min"] == -910
    assert summary["boundary_phase_bounds"]["top"]["global_z_log_abs_max"] == -390
    assert summary["boundary_phase_bounds"]["bottom"]["global_z_log_abs_min"] == -40


def test_allocation_denial_records_before_raising():
    events, calls = [], []
    def gate(label, facts):
        calls.append((label, facts))
        return False
    with pytest.raises(MemoryError, match="allocation gate denied"):
        candidate._admit("synthetic", {"Vec": 16, "rows": 4}, allocation_gate=gate, event=events.append)
    assert calls[0][1]["predicted_total_bytes"] == 20
    assert [e["stage"] for e in events] == ["allocation_before", "allocation_denied"]
    with pytest.raises(ValueError, match="nonnegative"):
        candidate._admit("bad", {"Vec": -1}, allocation_gate=gate, event=events.append)


def test_denied_metadata_never_enters_original_generator_or_creates_output(tmp_path):
    events = []
    with pytest.raises(MemoryError):
        candidate.build_metadata_packet(repo_root=tmp_path, output_dir=tmp_path/"not_created",
                                        allocation_gate=lambda *_: False, event=events.append)
    assert not (tmp_path/"not_created").exists()
    assert not any(e["stage"] == "original_inventory_generation_started" for e in events)
    assert events[-1]["stage"] == "metadata_partial_or_failed"


def test_original_two_functions_save_full_keys_before_legacy_H_failure():
    modes = tuple(fake_mode(0, 0, polarization=p) for p in ("s", "p"))
    cfg, calls = object(), []
    def original_builder(actual_modes, actual_cfg):
        assert actual_modes == modes and actual_cfg is cfg
        calls.append("legacy_H")
        raise FloatingPointError("synthetic legacy scalar H representability stop")
    def original_generator(actual_cfg):
        assert actual_cfg is cfg
        calls.append("original_generator")
        return modes
    captured = []
    def sink(actual_modes, keys):
        calls.append("persist_complete_keys")
        captured.append(json.loads(keys))
        assert actual_modes == modes
    with pytest.raises(FloatingPointError, match="legacy"):
        candidate._original_inventory_key_first(original_generator, original_builder, cfg, sink)
    assert calls == ["original_generator", "persist_complete_keys", "legacy_H"]
    assert captured == [[[0, "top", 0, 0, "s"], [1, "top", 0, 0, "p"]]]


def test_original_two_functions_return_exact_manifest_bytes_on_success():
    modes = (fake_mode(0, 0),)
    cfg, rows, encoded, digest = object(), ({"original_row": True},), b"original", "original-hash"
    def original_builder(actual_modes, actual_cfg):
        assert actual_modes == modes and actual_cfg is cfg
        return rows, encoded, digest
    def original_generator(actual_cfg):
        return modes
    actual_modes, actual_rows, actual_encoded, actual_digest, keys = candidate._original_inventory_key_first(
        original_generator, original_builder, cfg, lambda *_: None)
    assert actual_modes == modes and actual_rows is rows and actual_digest is digest and actual_encoded is encoded
    assert json.loads(keys) == [[0, "top", 0, 0, "s"]]


def test_component_admission_contains_all_live_buffers_and_scales_with_rows():
    facts = candidate.component_allocation_facts(200, 0, 882, 36)
    assert facts["raw_PETSc_Vecs_two_concurrent"] == 2*200*16
    assert facts["component_cache"] == facts["retained_previous_components"] == 0
    assert {"raw_numpy_retained_copy", "sparse_rows_values_retained", "component_staging_buffers",
            "sort_workspace_conservative", "output_numpy_and_serialization_workspace",
            "native_assembly_MPC_workspace_allowance", "Python_workspace_allowance"}.issubset(facts)
    assert sum(candidate.component_allocation_facts(400, 0, 882, 36).values()) > sum(facts.values())
    for args in [(0, 0, 882, 1), (20, -1, 882, 1), (20, 0, 0, 1), (20, 0, 882, 0)]:
        with pytest.raises(ValueError):
            candidate.component_allocation_facts(*args)


def test_reference_gate_uses_integral_scale_and_literal_zero_without_floor():
    assert candidate.reference_action_gate([0j], [0j], [0])["passed"]
    assert not candidate.reference_action_gate([1e-300+0j], [0j], [0])["passed"]
    assert candidate.reference_action_gate([5e-11+0j], [0j], [1])["passed"]
    assert not candidate.reference_action_gate([2e-10+0j], [0j], [1])["passed"]
    assert not candidate.reference_action_gate([1e-30+0j], [0j], [1e-30])["passed"]
    for primary, reference, scale in [([0j], [0j, 1j], [1]), ([complex(float("nan"))], [0j], [1]),
                                       ([0j], [0j], [-1]), ([0j], [0j], [float("inf")]),
                                       ([1e308+0j], [-1e308+0j], [1e308])]:
        with pytest.raises(ValueError):
            candidate.reference_action_gate(primary, reference, scale)


def test_streamed_compiled_evidence_copy_requires_exact_bytes(tmp_path):
    source, destination = tmp_path/"original.c", tmp_path/"saved.c"
    data = b"synthetic compiled-source bytes only\n"*100
    source.write_bytes(data)
    record = candidate._copy_pinned_file(source, destination, candidate.sha256(data))
    assert destination.read_bytes() == data and source.read_bytes() == data
    assert record["bytes"] == len(data) and record["sha256"] == candidate.sha256(data)
    with pytest.raises(ValueError, match="changed"):
        candidate._copy_pinned_file(source, tmp_path/"rejected.c", "wrong-hash")
    assert not (tmp_path/"rejected.c").exists() and source.read_bytes() == data


def write_synthetic_sealed_metadata(root):
    manifest = candidate.canonical({"synthetic_test_only": "not an original inventory"})
    keys = candidate.canonical([(0, "top", 0, 0, "s")])
    artifacts = {
        "physical_manifest": candidate._write_bytes(root/"original_physical_manifest.json", manifest),
        "ordered_keys": candidate._write_bytes(root/"original_ordered_keys.json", keys)}
    packet = {"status": "METADATA_COMPLETE_SURFACE_NOT_RUN", "artifacts": artifacts,
              "config_sha256": "synthetic-config"}
    saved = candidate._write_bytes(root/"metadata_packet.json", candidate.canonical(packet))
    seal = {"library_file_id": "synthetic-test-only", "library_version": 1, "library_readback_verified": True,
            "metadata_packet_sha256": saved["sha256"], "physical_manifest_sha256": artifacts["physical_manifest"]["sha256"],
            "ordered_keys_sha256": artifacts["ordered_keys"]["sha256"], "config_sha256": "synthetic-config"}
    return packet, seal


def test_seal_requires_library_readback_identity_and_all_exact_bytes(tmp_path):
    packet, seal = write_synthetic_sealed_metadata(tmp_path)
    assert candidate.validate_metadata_seal(metadata_dir=tmp_path, seal=seal) == json.loads(candidate.canonical(packet))
    for field, bad in [("library_readback_verified", False), ("library_file_id", None), ("library_version", None),
                       ("metadata_packet_sha256", "x"), ("physical_manifest_sha256", "x"),
                       ("ordered_keys_sha256", "x"), ("config_sha256", "x")]:
        with pytest.raises(ValueError):
            candidate.validate_metadata_seal(metadata_dir=tmp_path, seal={**seal, field: bad})
    (tmp_path/"original_physical_manifest.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact"):
        candidate.validate_metadata_seal(metadata_dir=tmp_path, seal=seal)


def functions_by_name():
    return {node.name: node for node in ast.walk(ast.parse(SOURCE.read_text()))
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def call_names(node):
    return [n.func.id if isinstance(n.func, ast.Name) else n.func.attr
            for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, (ast.Name, ast.Attribute))]


def test_AST_metadata_uses_only_original_physical_generator_and_builder():
    fn = functions_by_name()["_fresh_inventory"]
    calls = call_names(fn)
    assert calls.count("_original_inventory_key_first") == 1
    seam = call_names(functions_by_name()["_original_inventory_key_first"])
    assert seam.count("mode_generator") == seam.count("manifest_builder") == 1
    names = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
    assert {"outgoing_port_modes_3d", "build_ordered_mode_manifest"}.issubset(names)
    assert "_dtn_surface_quadrature_degree" in calls
    assert not {"_structured_hexa_mesh", "functionspace", "form", "assemble_vector", "FullspaceDtnCarrier"}.intersection(calls)
    assert "target_stage4_config" not in call_names(functions_by_name()["target_config"])


def test_AST_single_primary_form_no_volume_carrier_factor_or_PDE_calls():
    tree = ast.parse(SOURCE.read_text())
    calls = call_names(tree)
    assert calls.count("_ReusableSurfaceComponentAssembler") == 1
    assert calls.count("_structured_hexa_mesh") == 1
    assert not {"form", "TrialFunction", "assemble_matrix", "build_same_mesh_physical_action", "FullspaceDtnCarrier",
                "build_dynamic_dtn_action", "factor", "solve", "setUp"}.intersection(calls)
    primary = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and
                   isinstance(n.func, ast.Name) and n.func.id == "_ReusableSurfaceComponentAssembler")
    kwargs = {k.arg: k.value for k in primary.keywords}
    assert ast.literal_eval(kwargs["verify_compiled_gauss"]) is True
    assert "boundary_reference_z" in kwargs and "quadrature_degree" in kwargs
    surface = functions_by_name()["run_surface_stage"]
    named = [(n.lineno, n.func.id) for n in ast.walk(surface) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    positions = {name: min(line for line, value in named if value == name) for name in
                 ("validate_metadata_seal", "_fresh_inventory", "_bare_fixture", "_ReusableSurfaceComponentAssembler")}
    assert positions["validate_metadata_seal"] < positions["_fresh_inventory"] < positions["_bare_fixture"] < positions["_ReusableSurfaceComponentAssembler"]


def test_AST_existing_raw_and_masked_paths_and_correct_contraction_direction():
    surface = functions_by_name()["run_surface_stage"]
    calls = call_names(surface)
    assert calls.count("assemble_raw_mpc_vector") == 1 and calls.count("assemble_entries") == 1
    dot_calls = [n for n in ast.walk(surface) if isinstance(n, ast.Call) and
                 isinstance(n.func, ast.Attribute) and n.func.attr == "vdot"]
    assert len(dot_calls) == 2
    assert all(isinstance(n.args[0], ast.Subscript) and n.args[0].value.id == "states" for n in dot_calls)
