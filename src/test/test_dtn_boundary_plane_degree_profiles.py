"""Pure metadata/source contracts; these tests never qualify a live carrier.

The profile helper is AST-loaded alone to avoid importing the PDE stack.
Numerical532/Gauss/FFCx/MPC qualification remains a separately admitted run.
"""
import ast
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "solvers/dtn_boundary_plane_qualification.py"


def _profile_helper():
    tree = ast.parse(SOURCE.read_text())
    helper = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_qualification_degree_profile")
    namespace = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["_qualification_degree_profile"]


def _metadata(degree):
    dimension, qdegree, points = {2: (54, 19, 100), 4: (300, 23, 144)}[degree]
    space = SimpleNamespace(element=SimpleNamespace(
        basix_element=SimpleNamespace(degree=degree), space_dimension=dimension))
    mpc = SimpleNamespace(function_space=copy.deepcopy(space))
    rule = {"degree": qdegree, "facet_cell": "quadrilateral", "integral_type": "exterior_facet",
            "points": {"shape": [points, 2], "dtype": "float64"},
            "weights": {"shape": [points], "dtype": "float64"}}
    primary = {name: {"rules": [copy.deepcopy(rule)]}
               for name in ("top/0", "top/1", "bottom/0", "bottom/1")}
    context = {"element_degree": degree, "gauss": {"degree": qdegree}}
    return {"degree": degree, "cfg": SimpleNamespace(nedelec_degree=degree),
            "setup": {"spaces": {degree: space}, "floquets": {degree: SimpleNamespace(mpc=mpc)}},
            "dtn_action": SimpleNamespace(carrier=SimpleNamespace(assembly_context=context)),
            "dtn_quadrature_degree": qdegree, "compiled_surface_gauss_identity": primary}


@pytest.mark.parametrize("degree", [2, 4])
def test_profile_records_actual_requested_degree_basis_and_gauss(degree):
    metadata = _metadata(degree)
    profile = _profile_helper()(metadata)
    assert profile == {"degree": degree, "element_degree": degree,
                       "local_space_dimension": {2: 54, 4: 300}[degree],
                       "quadrature_degree": {2: 19, 4: 23}[degree],
                       "primary_facet_points": {2: 100, 4: 144}[degree]}


@pytest.mark.parametrize("degree", [1, 3, 6, 4.0, True])
def test_other_degrees_or_narrowing_from_noninteger_values_are_rejected(degree):
    metadata = _metadata(4)
    metadata["degree"] = degree
    with pytest.raises(ValueError, match="integer degree 2 or 4"):
        _profile_helper()(metadata)


@pytest.mark.parametrize("failure", ["cfg", "basis", "local_dimension", "MPC_basis", "MPC_dimension",
                                     "context_degree", "bundle_Gauss", "context_Gauss", "extra_level"])
def test_p4_cannot_inherit_p2_basis_MPC_or_gauss_metadata(failure):
    metadata = _metadata(4)
    space = metadata["setup"]["spaces"][4]
    mpc_space = metadata["setup"]["floquets"][4].mpc.function_space
    context = metadata["dtn_action"].carrier.assembly_context
    if failure == "cfg":
        metadata["cfg"].nedelec_degree = 2
    elif failure == "basis":
        space.element.basix_element.degree = 2
    elif failure == "local_dimension":
        space.element.space_dimension = 54
    elif failure == "MPC_basis":
        mpc_space.element.basix_element.degree = 2
    elif failure == "MPC_dimension":
        mpc_space.element.space_dimension = 54
    elif failure == "context_degree":
        context["element_degree"] = 2
    elif failure == "bundle_Gauss":
        metadata["dtn_quadrature_degree"] = 19
    elif failure == "context_Gauss":
        context["gauss"]["degree"] = 19
    else:
        metadata["setup"]["spaces"][2] = space
    with pytest.raises(ValueError):
        _profile_helper()(metadata)


@pytest.mark.parametrize("failure", ["missing_form", "two_rules", "p2_nodes", "p2_degree",
                                     "point_dimension", "weight_count", "points_dtype", "facet_cell"])
def test_actual_four_primary_gauss_inventories_must_match_the_p4_profile(failure):
    metadata = _metadata(4)
    primary = metadata["compiled_surface_gauss_identity"]
    rule = primary["bottom/1"]["rules"][0]
    if failure == "missing_form":
        primary.pop("bottom/1")
    elif failure == "two_rules":
        primary["bottom/1"]["rules"].append(copy.deepcopy(rule))
    elif failure == "p2_nodes":
        rule["points"]["shape"] = [100, 2]
    elif failure == "p2_degree":
        rule["degree"] = 19
    elif failure == "point_dimension":
        rule["points"]["shape"] = [144, 3]
    elif failure == "weight_count":
        rule["weights"]["shape"] = [143]
    elif failure == "points_dtype":
        rule["points"]["dtype"] = "float32"
    else:
        rule["facet_cell"] = "triangle"
    with pytest.raises(ValueError):
        _profile_helper()(metadata)


def _proof_blocks():
    tree = ast.parse(SOURCE.read_text())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == "qualify_boundary_plane_bundle")
    transaction = next(node for node in function.body if isinstance(node, ast.Try))
    blocks = {}
    for node in transaction.body:
        if isinstance(node, ast.For):
            name = ast.unparse(node.target)
            if name in ("gauge", "(index, (mode, new_entry))", "(active_bundle, label)"):
                blocks[name] = node
    blocks["failure_handler"] = transaction.handlers[0]
    blocks["lifecycle_finally"] = ast.Module(body=transaction.finalbody, type_ignores=[])
    blocks["LIVE_COMPONENT_GATES"] = next(node for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
          and target.id == "LIVE_COMPONENT_GATES" for target in node.targets))
    return {name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
            for name, node in blocks.items()}


def test_degree_extension_preserves_the_frozen_literal_mode_output_and_lifecycle_gates():
    # These are AST identities of the reviewed 4cc0f76 numerical proof blocks,
    # not successful numerical fixture measurements.
    assert _proof_blocks() == {
        "gauge": "aa40f5ca22c8784dd21e372c943af8ad72a4616287d4a710f268f68952c80ca2",
        "(index, (mode, new_entry))": "9360df7224c19501304ec1569c89a8849bdd624637c26d8cf72bc196cf241a9d",
        "(active_bundle, label)": "e6aab2257273308d55cb4afd7d7723003be70441b83c2ac4edc869e4ad8b81aa",
        "failure_handler": "8067c9cb419a88a6940dc3af0a8181603b64b4893f0b393a606bb9be5e0e04ad",
        "lifecycle_finally": "c02d11bcb2a8768bec518be9a631d89e747d3347f0115800b38ec867d2cc11ab",
        "LIVE_COMPONENT_GATES": "caf5e269e761379d540c020cfb93236dc28af0f4733173deb74c8978ddc15507",
    }
