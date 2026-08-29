"""Focused contracts for the J2a minimal precompile child."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.solvers import fullspace_same_mesh_hcurl_pmg_jit as jit


GROUP_ROLES = {
    "positive-p6": (2, ("positive_p6_action", "positive_p6_bilinear")),
    "positive-p3": (1, ("positive_p3_bilinear",)),
    "positive-p1": (1, ("positive_p1_bilinear",)),
    "dtn-surface": (4, ("dtn_surface_top_0", "dtn_surface_top_1", "dtn_surface_bottom_0", "dtn_surface_bottom_1")),
    "incident-rhs": (1, ("incident_top_traction",)),
    "physical-volume": (1, ("physical_volume_action",)),
}


@pytest.mark.parametrize("group", tuple(GROUP_ROLES))
def test_group_dispatch_returns_minimal_form_facts(monkeypatch, group):
    cfg = SimpleNamespace(nedelec_degree=6, mesh_target_size=10.0, lambda0=13.5)
    comm = SimpleNamespace(size=1)
    count, roles = GROUP_ROLES[group]
    builders = {
        "positive-p6": "_build_positive_p6",
        "positive-p3": "_build_positive_coarse",
        "positive-p1": "_build_positive_coarse",
        "dtn-surface": "_build_dtn_surface",
        "incident-rhs": "_build_incident_rhs",
        "physical-volume": "_build_physical_volume",
    }

    def fake_builder(_cfg, _comm, _jit_options, *, _group=group):
        forms = [
            {"role": role, "rank": 1 if "bilinear" not in role else 2, "kind": "fake"}
            for role in roles
        ]
        return jit._facts(_group, 6 if _group != "positive-p3" and _group != "positive-p1" else int(_group[-1]), forms, _jit_options)

    monkeypatch.setattr(jit, builders[group], fake_builder)
    if group == "positive-p3":
        monkeypatch.setattr(
            jit,
            "_build_positive_coarse",
            lambda cfg, comm, degree, options: fake_builder(cfg, comm, options),
        )
    elif group == "positive-p1":
        monkeypatch.setattr(
            jit,
            "_build_positive_coarse",
            lambda cfg, comm, degree, options: fake_builder(cfg, comm, options),
        )
    facts = jit.build_minimal_jit_group(cfg, comm, group)
    assert facts["compiled_form_count"] == count
    assert tuple(facts["form_roles"]) == roles
    assert facts["jit_options"] == {}
    assert all(value is False for value in facts["objects"].values())


def test_selected_call_sites_use_empty_mapping_and_generic_defaults_remain():
    root = Path(__file__).resolve().parents[2]
    setup = (root / "src/solvers/fullspace_same_mesh_hcurl_pmg_setup.py").read_text()
    physical = (root / "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py").read_text()
    global_source = (root / "src/solvers/fullspace_same_mesh_hcurl_pmg_global.py").read_text()
    dtn = (root / "src/solvers/dtn_port_3d.py").read_text()
    jit_source = (root / "src/solvers/fullspace_same_mesh_hcurl_pmg_jit.py").read_text()
    assert "SAME_MESH_JIT_OPTIONS = MappingProxyType({})" in setup
    assert setup.count("jit_options=SAME_MESH_JIT_OPTIONS") >= 3
    assert "jit_options=dict(SAME_MESH_JIT_OPTIONS)" in setup
    assert "include_positive_coefficients=True" in jit_source
    assert jit_source.count("include_positive_coefficients=False") == 3
    assert physical.count("jit_options=SAME_MESH_JIT_OPTIONS") >= 3
    assert "jit_options: Mapping[str, Any] | None = None" in global_source
    assert "jit_options: Mapping[str, Any] | None = None" in dtn
    assert ast.parse(global_source)
    assert ast.parse(dtn)


def test_child_is_lazy_and_paths_record_is_exclusive(tmp_path):
    root = Path(__file__).resolve().parents[2]
    runner_path = root / "benchmarks/run_task038_full3d_jit_precompile.py"
    tree = ast.parse(runner_path.read_text())
    forbidden = ("numpy", "dolfinx", "petsc4py", "mpi4py", "src")
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        assert not any(
            name == bad or name.startswith(bad + ".")
            for name in names
            for bad in forbidden
        )

    runner = importlib.import_module("benchmarks.run_task038_full3d_jit_precompile")
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir()
    cache = artifact_root / "jit_cache"
    cache.mkdir()
    record = artifact_root / "record.json"
    assert runner._prepare_paths(cache, record) == (cache.resolve(), record.resolve())
    runner._write_record(record, {"schema": "test", "raw_facts_only": True})
    assert record.read_bytes().endswith(b"\n")
    with pytest.raises(FileExistsError):
        runner._prepare_paths(cache, record)
