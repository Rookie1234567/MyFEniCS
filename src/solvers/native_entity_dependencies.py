"""New consumption envelopes; old immutable V40 packets are never rewritten."""

import ast
import hashlib
import json
import subprocess
from pathlib import Path

from src.runners.task042_shared import write_json
from src.solvers.native_recovery_packets import sha

ROOT = Path(__file__).resolve().parents[2]
STAGE_SOURCES = {
    "geometry": {
        "src/solvers/target_boundary_witness.py": ["build_patch"],
        "src/solvers/native_integration_study.py": ["native_literal"],
        "src/geometry/mesh_builder_3d.py": ["_mark_cells", "_mark_boundary_facets"],
        "src/solvers/target_port_preparation.py": [
            "target_config",
            "geometry_contract",
        ],
    },
    "classes": {
        "src/solvers/common_3d_forms.py": None,
        "src/solvers/hcurl_assembly_time_condensation.py": None,
    },
    "quadrature": {
        "src/solvers/native_integration_study.py": ["polynomial_volume"],
        "src/solvers/native_recovery_study.py": ["orient_basix_tensor"],
    },
    "recovery": {
        "src/solvers/native_boundary_adapter.py": None,
        "src/solvers/p6_cell_condensed_action.py": None,
        "src/solvers/native_recovery_study.py": ["loaded_objects", "recover"],
    },
}

# Full modules close helper/global/default dependencies as well as the selected
# function ASTs above. Runner/document changes are outside these numerical groups.
HELPER_SOURCES = {
    "geometry": (
        "src/constraints/floquet_3d.py",
        "src/constraints/floquet_3d_high_order.py",
        "src/constraints/high_order_floquet_trace.py",
        "src/solvers/native_entity_topology.py",
        "src/common/config_3d.py",
        "src/common/optical_material_table.py",
    ),
    "classes": ("src/solvers/hcurl_affine_isotropic_tensor.py",),
    "quadrature": ("src/solvers/hcurl_affine_isotropic_tensor.py",),
    "recovery": (
        "src/solvers/native_recovery_packets.py",
        "src/solvers/native_entity_adapter.py",
        "src/solvers/native_entity_protocol.py",
    ),
}


def dependency_closure(group, source=None):
    """Consumer-derived file identities; no dependence on a saved identity."""
    result = {}
    for name in sorted(set(STAGE_SOURCES[group]) | set(HELPER_SOURCES[group])):
        data = (
            (ROOT / name).read_bytes()
            if source is None
            else subprocess.check_output(
                [
                    "git",
                    "-c",
                    "gc.auto=0",
                    "-c",
                    "maintenance.auto=false",
                    "show",
                    source + ":" + name,
                ],
                cwd=ROOT,
            )
        )
        result[name] = hashlib.sha256(data).hexdigest()
    return result


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def semantic_hashes(group, source=None):
    out = {}
    for name, functions in STAGE_SOURCES[group].items():
        data = (
            (ROOT / name).read_bytes()
            if source is None
            else subprocess.check_output(
                [
                    "git",
                    "-c",
                    "gc.auto=0",
                    "-c",
                    "maintenance.auto=false",
                    "show",
                    source + ":" + name,
                ],
                cwd=ROOT,
            )
        )
        if functions is None:
            out[name] = hashlib.sha256(data).hexdigest()
        else:
            tree = ast.parse(data)
            nodes = {
                n.name: n
                for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.ClassDef))
            }
            for function in functions:
                if function not in nodes:
                    raise ValueError(
                        "missing stage dependency " + name + ":" + function
                    )
                out[name + ":" + function] = hashlib.sha256(
                    ast.dump(nodes[function], include_attributes=False).encode()
                ).hexdigest()
    return out


def validate_envelope(envelope, expected):
    if (
        envelope.get("schema") != "native-entity-consumption.v1"
        or envelope.get("commit") is not True
    ):
        raise ValueError("consumption commit/schema")
    required = (
        "physical",
        "material",
        "phase",
        "basis",
        "owner_protocol",
        "index_dtype",
        "scalar_dtype",
        "axes",
        "modes",
        "slave_semantics",
        "stage_dependencies",
        "tags",
        "q",
    )
    if any(name not in expected for name in required):
        raise ValueError("incomplete live consumer identity")
    for name in expected:
        if name not in envelope:
            raise ValueError("missing live consumption identity " + name)
        if envelope[name] != expected[name]:
            raise ValueError("consumption identity " + name)
    if envelope["identity_sha256"] != digest({k: envelope[k] for k in expected}):
        raise ValueError("consumption envelope content")
    for item in envelope["parents"]:
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("immutable consumption parent hash")
    for binding in envelope["class_bindings"]:
        system = json.loads(Path(binding["system_path"]).read_text())
        actual = system["metadata"]["classes"]
        if actual != binding["classes"]:
            raise ValueError("system class inventory binding")
        for item in actual:
            if (
                sha(Path(binding["system_path"]).parent / (item["name"] + ".json"))
                != item["sha256"]
            ):
                raise ValueError("system class manifest hash")
    return envelope


def publish_envelope(path, expected, *, parents, class_bindings):
    path = Path(path)
    if path.exists():
        raise FileExistsError("immutable consumption envelope")
    row = dict(
        expected,
        schema="native-entity-consumption.v1",
        commit=True,
        identity_sha256=digest(expected),
        parents=parents,
        class_bindings=class_bindings,
    )
    validate_envelope(row, expected)
    write_json(path, row)
    return row
