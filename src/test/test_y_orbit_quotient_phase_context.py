"""Static source/metadata contracts; these tests never import numerical modules.

They guard wiring/default boundaries only. They do not qualify phase/MPC,
raw/masked equivalence, a live basis/Gauss rule, or a quotient PDE operator.
"""

import ast
import copy
import inspect
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PATHS = (
    "src/constraints/floquet_3d.py", "src/constraints/floquet_3d_high_order.py",
    "src/solvers/fullspace_same_mesh_hcurl_pmg_global.py",
    "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
    "src/solvers/fullspace_dtn_action.py", "src/solvers/dtn_boundary_phase_gauge.py",
    "src/solvers/y_orbit_quotient_context.py",
)


def _source(relative):
    return (ROOT / relative).read_text()


def _function(relative, name):
    return next(node for node in ast.walk(ast.parse(_source(relative)))
                if isinstance(node, ast.FunctionDef) and node.name == name)


def _calls(node, name):
    return [call for call in ast.walk(node) if isinstance(call, ast.Call)
            and ((isinstance(call.func, ast.Name) and call.func.id == name)
                 or (isinstance(call.func, ast.Attribute) and call.func.attr == name))]


@pytest.mark.parametrize("relative", PATHS)
def test_quotient_sources_parse_without_imports_or_execution(relative):
    ast.parse(_source(relative), filename=relative)


def test_public_phase_override_is_materialized_before_original_finalize():
    public = _function(PATHS[0], "build_double_floquet_mpc")
    high = _function(PATHS[0], "_build_double_floquet_mpc_high_order")
    arrays = _function(PATHS[1], "build_high_order_constraint_data")
    assert "research_phase_override" in [arg.arg for arg in public.args.kwonlyargs]
    assert len(_calls(high, "finalize")) == 1
    assert any(call.lineno < _calls(high, "finalize")[0].lineno
               for call in _calls(high, "build_high_order_constraint_data"))
    assert len(_calls(arrays, "materialize")) == 1
    assert any(isinstance(node, ast.IfExp)
               and ast.unparse(node.test) == "materialized_override is None"
               and ast.unparse(node.body) == "phase * block.coefficient_transform[row, :]"
               for node in ast.walk(arrays))
    assert not any(isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Attribute) and target.attr in {"incident_phi_deg", "incident_theta_deg"}
        for target in node.targets) for node in ast.walk(high))


def test_local_setup_retains_original_call_when_override_absent():
    setup = _function(PATHS[2], "_build_same_mesh_levels")
    guarded = next(node for node in ast.walk(setup) if isinstance(node, ast.If)
                   and ast.unparse(node.test) == "research_phase_override is None")
    old_call = _calls(guarded.body[0], "build_double_floquet_mpc")[0]
    research_call = _calls(guarded.orelse[0], "build_double_floquet_mpc")[0]
    assert not old_call.keywords
    assert [kw.arg for kw in research_call.keywords] == ["research_phase_override"]


def test_quotient_context_cannot_generate_or_rephase_physical_modes():
    source = _source(PATHS[6])
    tree = ast.parse(source)
    assert not _calls(tree, "outgoing_port_modes_3d")
    assert not _calls(tree, "build_dynamic_mode_inventory")
    assert not _calls(tree, "sqrt") and not _calls(tree, "angle")
    assert "((int(modes[i].n)-b)//REPLICATION_COUNT) % LOCAL_Y_CELLS" in source
    assert "((int(modes[i].n)-self.twist_index)//REPLICATION_COUNT) % LOCAL_Y_CELLS" in source
    assert 'SECTOR_MODE_COUNTS = (228, 304)' in source
    assert 'GLOBAL_MODE_COUNT = 532' in source
    assert '4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951' in source
    assert 'build_ordered_mode_manifest(modes, global_cfg)' in source
    assert 'self.theta != theta or self.eta != eta or self.tau != eta**2' in source
    assert 'original_mode_rows' in source and 'copy_to_retain' not in source


def test_global_inventory_is_selected_before_local_surface_assembly():
    function = _function(PATHS[3], "build_same_mesh_physical_action")
    select = _calls(function, "select_inventory")[0]
    surface = _calls(function, "_surface_assemblers")[0]
    assert select.lineno < surface.lineno
    source = _source(PATHS[3])
    assert 'qdegree = _dtn_surface_quadrature_degree(physical_cfg, list(mode_inventory[0]))' in source
    assert '"mode_sha256": mode_sha' in source
    assert '"global_mode_indices": quotient_context.original_mode_indices' in source
    assert '"qbase": quotient_context.twist_index' in source
    assert 'incident_projections = None' in source
    rhs = _function(PATHS[3], "build_physical_rhs")
    assert isinstance(rhs.body[1], ast.If)
    assert 'quotient_context' in ast.unparse(rhs.body[1].test)
    assert any(isinstance(node, ast.Raise) for node in ast.walk(rhs.body[1]))


def test_local_identity_keeps_contiguous_indices_and_original_mapping():
    source = _source(PATHS[4])
    assert 'if identity.get("mode_index") != index:' in source
    assert '"original_mode_index": quotient_context.original_mode_indices[index]' in source
    assert '"original_mode_row": manifest_rows[index]' in source
    assert '"local_branch_index": quotient_context.local_branch_indices[index]' in source
    assert 'denominator*2, global_h' in source
    assert 'manifest_rows, _manifest_sha = quotient_rows, quotient_manifest_sha' in source
    assert 'result.physical_generator_manifest_sha256 = _manifest_sha' in source


def test_actual_local_discrete_and_source_identity_is_explicit():
    source = _source(PATHS[5])
    for token in ('quotient_context.identity()', 'quotient_context.sha256',
                  '_mpc_expansion_width(mpc, rows)', 'actual_finalized_mpc_max_expansion_width',
                  'np.unique(mesh.geometry.x[:, axis])', 'element.degree', 'qdegree',
                  '"y_orbit_quotient_context.py"', '"floquet_3d_high_order.py"'):
        assert token in source


def test_raw_observer_uses_actual_vectors_and_unchanged_masks_with_bounded_lifetime():
    components = _function(PATHS[4], "_raw_owned_surface_components")
    observer = _function(PATHS[4], "_observe_raw_mode")
    carrier = _function(PATHS[4], "build_fullspace_dtn_carrier_from_surface")
    assert len(_calls(components, "assemble_raw_mpc_vector")) == 1
    assert len(_calls(components, "_vec_nonzero_owned_entries")) == 1
    assert any(isinstance(node, ast.Try) and _calls(node.finalbody[0], "destroy")
               for node in ast.walk(components))
    assert len(_calls(carrier, "_combine_owned_entries")) == 2
    source = _source(PATHS[4])
    assert 'if raw_mode_observer is None:\n            components = components_for(mode)' in source
    assert 'del raw_components, components, component_diagnostics' in source
    assert 'copy=True' in ast.unparse(components)
    assert 'writeable = False' in ast.unparse(components)
    assert 'raw_vectors_destroyed_before_callback' in ast.unparse(observer)
    assert 'single_D_conjugation' in ast.unparse(observer)
    assert 'array_ownership' in ast.unparse(observer)
    assert 'raw_minus_stored_norm_global' in source
    assert 'absolute_sparse_floor": 1e-30' in source
    assert 'relative_sparse_cutoff": 1e-13' in source


def _isolated_signature(function):
    """Compile only its declared signature with an inert body, without imports."""
    stub = copy.deepcopy(function)
    stub.body = [ast.Pass()]
    stub.decorator_list = []
    stub.returns = None
    for argument in (*stub.args.posonlyargs, *stub.args.args, *stub.args.kwonlyargs):
        argument.annotation = None
    if stub.args.vararg is not None:
        stub.args.vararg.annotation = None
    if stub.args.kwarg is not None:
        stub.args.kwarg.annotation = None
    module = ast.fix_missing_locations(ast.Module(body=[stub], type_ignores=[]))
    namespace = {}
    exec(compile(module, "<isolated Floquet signature>", "exec"), namespace)
    return inspect.signature(namespace[function.name])


def test_public_high_order_calls_bind_to_actual_signature_default_and_explicit():
    """Catch a misplaced override keyword before any DOLFINx/project import."""
    public = _function(PATHS[0], "build_double_floquet_mpc")
    high = _function(PATHS[0], "_build_double_floquet_mpc_high_order")
    legacy = _function(PATHS[0], "_build_double_floquet_mpc_p2_trace")
    signature = _isolated_signature(high)
    assert signature.parameters["research_phase_override"].kind == inspect.Parameter.KEYWORD_ONLY
    assert signature.parameters["research_phase_override"].default is None
    calls = _calls(public, "_build_double_floquet_mpc_high_order")
    assert len(calls) == 2
    assert sorted(bool(call.keywords) for call in calls) == [False, True]
    for call in calls:
        signature.bind(*[object() for _ in call.args],
                       **{keyword.arg: object() for keyword in call.keywords})
    assert "research_phase_override" not in _isolated_signature(legacy).parameters
    # A loaded override name in this function must be declared locally.
    local_arguments = {arg.arg for arg in (*high.args.args, *high.args.kwonlyargs)}
    assert any(isinstance(node, ast.Name) and node.id == "research_phase_override"
               and isinstance(node.ctx, ast.Load) for node in ast.walk(high))
    assert "research_phase_override" in local_arguments
