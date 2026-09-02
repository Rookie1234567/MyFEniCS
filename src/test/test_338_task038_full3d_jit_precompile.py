"""Focused contracts for the J3 split physical precompile child."""

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
    "dtn-surface": (
        8,
        (
            "dtn_surface_top_0",
            "dtn_surface_top_1",
            "dtn_surface_bottom_0",
            "dtn_surface_bottom_1",
        )
        * 2,
    ),
    "incident-rhs": (1, ("incident_top_traction",)),
    "physical-volume-curl": (2, ("physical_volume_curl_action",) * 2),
    "physical-volume-mass": (2, ("physical_volume_mass_action",) * 2),
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
        "physical-volume-curl": "_build_physical_volume_component",
        "physical-volume-mass": "_build_physical_volume_component",
    }

    def fake_facts(_group, degree, _jit_options, **extra):
        multi_degree = group in {
            "dtn-surface",
            "physical-volume-curl",
            "physical-volume-mass",
        }
        form_degrees = (6, 3) if multi_degree else (degree,)
        form_roles = roles[: len(roles) // len(form_degrees)]
        forms = []
        for form_degree in form_degrees:
            for role in form_roles:
                form = {
                    "role": role,
                    "rank": 1 if "bilinear" not in role else 2,
                    "kind": "fake",
                }
                if multi_degree:
                    form["degree"] = form_degree
                forms.append(form)
        if multi_degree:
            extra["degrees"] = [6, 3]
            if group != "dtn-surface":
                extra["action_degrees"] = [6, 3]
        return jit._facts(_group, degree, forms, _jit_options, **extra)

    def fake_builder(_cfg, _comm, _jit_options):
        degree = 6 if group not in {"positive-p3", "positive-p1"} else int(group[-1])
        return fake_facts(group, degree, _jit_options)

    if group in {"physical-volume-curl", "physical-volume-mass"}:
        expected_component = "curl" if group.endswith("curl") else "mass"
        seen_components = []

        def fake_component(_cfg, _comm, _jit_options, component):
            seen_components.append(component)
            return fake_facts(
                group,
                6,
                _jit_options,
                component=component,
                component_count=1,
            )

        monkeypatch.setattr(
            jit,
            "_build_physical_volume_component",
            fake_component,
        )
    elif group in {"positive-p3", "positive-p1"}:
        monkeypatch.setattr(
            jit,
            "_build_positive_coarse",
            lambda _cfg, _comm, degree, options: fake_facts(
                group, degree, options
            ),
        )
    else:
        monkeypatch.setattr(jit, builders[group], fake_builder)
    facts = jit.build_minimal_jit_group(cfg, comm, group)
    assert facts["compiled_form_count"] == count
    assert tuple(facts["form_roles"]) == roles
    assert facts["jit_options"] == {}
    assert all(value is False for value in facts["objects"].values())
    if group in {"dtn-surface", "physical-volume-curl", "physical-volume-mass"}:
        assert facts["degrees"] == [6, 3]
        assert tuple(form["degree"] for form in facts["forms"]) == (
            (6,) * (count // 2) + (3,) * (count // 2)
        )
        if group != "dtn-surface":
            assert facts["action_degrees"] == [6, 3]
    if group in {"physical-volume-curl", "physical-volume-mass"}:
        assert seen_components == [expected_component]
        assert facts["component"] == expected_component


def test_dtn_surface_builder_uses_p6_then_p3_on_one_mesh(monkeypatch):
    from src.solvers import fullspace_same_mesh_hcurl_pmg_physical as physical

    cfg = SimpleNamespace()
    comm = SimpleNamespace(size=1)
    spaces = {6: object(), 3: object()}
    mesh_data = object()
    levels = {"spaces": spaces, "mesh_data": mesh_data}
    level_calls = []
    assembler_calls = []

    def fake_levels(_cfg, _comm, degrees, *, include_positive_coefficients):
        level_calls.append((degrees, include_positive_coefficients))
        return levels

    def fake_assemblers(space, mesh_data_arg, cfg_arg, qdegree, *, jit_options):
        assembler_calls.append((space, mesh_data_arg, cfg_arg, qdegree, jit_options))
        return {"temporary": object()}

    monkeypatch.setattr(jit, "_levels_for_degrees", fake_levels)
    monkeypatch.setattr(jit, "_mode_facts", lambda _cfg: (80, "mode-sha", 17))
    monkeypatch.setattr(physical, "_surface_assemblers", fake_assemblers)

    facts = jit._build_dtn_surface(cfg, comm, {})

    assert level_calls == [((6, 3), False)]
    assert [call[0] for call in assembler_calls] == [spaces[6], spaces[3]]
    assert all(call[1] is mesh_data for call in assembler_calls)
    assert [call[3] for call in assembler_calls] == [17, 17]
    assert facts["compiled_form_count"] == 8
    assert tuple(form["degree"] for form in facts["forms"]) == (6,) * 4 + (3,) * 4
    assert facts["degrees"] == [6, 3]
    assert "action_degrees" not in facts
    assert facts["mode_count"] == 80
    assert facts["dtn_quadrature_degree"] == 17
    assert all(value is False for value in facts["objects"].values())


@pytest.mark.parametrize("component", ("curl", "mass"))
def test_physical_volume_builder_compiles_p6_then_p3_action(
    monkeypatch, component
):
    import sys
    import types

    cfg = SimpleNamespace()
    comm = SimpleNamespace(size=1)
    spaces = {6: object(), 3: object()}
    mesh_data = SimpleNamespace(mesh=object(), cell_tags=object())
    levels = {"spaces": spaces, "mesh": mesh_data.mesh, "mesh_data": mesh_data}
    level_calls = []
    terms = []
    compile_calls = []

    ufl = types.ModuleType("ufl")
    ufl.TrialFunction = lambda space: ("trial", space)
    ufl.TestFunction = lambda space: ("test", space)
    ufl.Measure = lambda *args, **kwargs: (args, kwargs)
    ufl.action = lambda form, coefficient: {
        "form": form,
        "space": coefficient.space,
    }

    dolfinx = types.ModuleType("dolfinx")
    fem = types.ModuleType("dolfinx.fem")

    class FakeFunction:
        def __init__(self, space):
            self.space = space

    fem.Function = FakeFunction
    dolfinx.fem = fem

    common = types.ModuleType("src.solvers.common_3d_forms")
    common._validate_physical_split_profile = lambda _cfg: None

    def fake_terms(_cfg, trial, test, dx):
        terms.append((trial, test, dx))
        return ({"name": "curl"}, {"name": "mass"})

    common._build_physical_volume_terms = fake_terms
    monkeypatch.setitem(sys.modules, "ufl", ufl)
    monkeypatch.setitem(sys.modules, "dolfinx", dolfinx)
    monkeypatch.setitem(sys.modules, "dolfinx.fem", fem)
    monkeypatch.setitem(sys.modules, "src.solvers.common_3d_forms", common)

    def fake_levels(_cfg, _comm, degrees, *, include_positive_coefficients):
        level_calls.append((degrees, include_positive_coefficients))
        return levels

    monkeypatch.setattr(jit, "_levels_for_degrees", fake_levels)
    monkeypatch.setattr(
        jit,
        "_compile_form",
        lambda form, _options: compile_calls.append(form),
    )

    facts = jit._build_physical_volume_component(cfg, comm, {}, component)

    assert level_calls == [((6, 3), False)]
    assert len(terms) == 2
    assert [call["space"] for call in compile_calls] == [spaces[6], spaces[3]]
    assert [call["form"]["name"] for call in compile_calls] == [component] * 2
    assert facts["compiled_form_count"] == 2
    assert tuple(form["degree"] for form in facts["forms"]) == (6, 3)
    assert facts["degrees"] == [6, 3]
    assert facts["action_degrees"] == [6, 3]
    assert facts["component"] == component
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
    assert tuple(jit.JIT_GROUPS) == tuple(GROUP_ROLES)
    assert jit.JIT_GROUP_SCHEMA.endswith(".v3")
    assert "_build_variational_forms" not in jit_source
    assert "_build_physical_volume_terms" in jit_source
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
