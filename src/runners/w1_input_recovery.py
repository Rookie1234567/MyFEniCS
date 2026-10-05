"""One immutable mode-only recovery. Original numerical functions are unchanged."""

import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import types


def selected_functions(path, names, namespace):
    """Execute exact named AST nodes, avoiding an unrelated top-level campaign."""
    tree = ast.parse(Path(path).read_text())
    nodes = [
        n
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names
    ]
    if {n.name for n in nodes} != set(names):
        raise ValueError("W1_FROZEN_REQUIRED_FUNCTIONS")
    future = ast.parse("from __future__ import annotations").body
    exec(
        compile(ast.Module(body=future + nodes, type_ignores=[]), str(path), "exec"),
        namespace,
    )


def recover(snapshot, binding, *, atomic_json, file_receipt):
    import dataclasses
    from fractions import Fraction
    import numpy as np

    root = Path(__file__).resolve().parents[2]
    contract_path = root / "src/io/w1_receiver_contract.py"
    # Current provenance code is loaded before the frozen src import namespace.
    import importlib.util

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    contract = load("_recovery_contract", contract_path)
    provenance = load("_recovery_provenance", root / "src/io/w1_reproduced_input.py")
    sys.path.insert(0, str(snapshot))
    # Only the five exact metadata helpers are exposed. No FE assembly imports
    # from the large dtn solver are needed or executed for mode recovery.
    port = types.ModuleType("src.solvers.dtn_port_3d")
    port.__package__ = "src.solvers"
    port.__file__ = str(snapshot / "src/solvers/dtn_port_3d.py")
    port.np = np
    selected_functions(
        port.__file__,
        [
            "_outward_normal",
            "_mode_boundary_z",
            "_mode_boundary_phase",
            "_mode_projection_denominator",
            "_traction_vector",
        ],
        port.__dict__,
    )
    sys.modules[port.__name__] = port
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory

    ns = {"replace": dataclasses.replace, "SCALE_TO_ORIGINAL": Fraction(135, 7)}
    selected_functions(
        snapshot / "benchmarks/run_task40_v5_target_ledger.py",
        ["_target_config", "_target_mode_physical_identity"],
        ns,
    )
    cfg = simulation_config_3d_from_normalized(
        load_and_resolve(snapshot / provenance.SOURCE_INPUT).as_jsonable()
    )
    target = ns["_target_config"](cfg)
    # This is the single permitted generator invocation; serialization below
    # uses the same frozen function on returned rows, without a second build.
    modes, rows, original_digest = build_dynamic_mode_inventory(target)
    from src.solvers.fullspace_dtn_action import (
        _canonical_json_bytes,
        FULLSPACE_DTN_MANIFEST_SCHEMA,
        FULLSPACE_DTN_PROFILE,
    )

    data = _canonical_json_bytes(
        {
            "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
            "profile": FULLSPACE_DTN_PROFILE,
            "mode_count": len(rows),
            "modes": rows,
        }
    )
    path = Path(binding["spec"]["manifest_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    reopened = path.read_bytes()
    keys = [[r["side"], r["m"], r["n"], r["polarization"]] for r in rows]
    key_sha = hashlib.sha256(
        json.dumps(keys, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    physical = ns["_target_mode_physical_identity"](target)
    manifest_sha = hashlib.sha256(reopened).hexdigest()
    inventory = {
        "target_mode_physical_identity_sha256": provenance.canonical_sha(physical),
        "ordered_mode_key_sha256": key_sha,
        "ordered_physical_mode_manifest_sha256": original_digest,
        "mode_manifest_bytes_sha256": manifest_sha,
    }
    passed = (
        len(reopened) == contract.MANIFEST_BYTES
        and manifest_sha == contract.MANIFEST_SHA
        and len(modes) == 32060
        and len(set(map(tuple, keys))) == 32060
        and key_sha == contract.KEY_SHA
        and original_digest == manifest_sha
        and provenance.canonical_sha(physical) == contract.PHYSICAL_SHA
        and provenance.canonical_sha(inventory) == contract.INVENTORY_SHA
    )
    files = json.loads(Path(binding["contract_source_manifest_path"]).read_text())[
        "files"
    ]
    result = {
        "status": "BITWISE_REPRODUCED_INPUT_PENDING_RECEIPT"
        if passed
        else "BITWISE_REPRODUCTION_FAILED",
        "generation_count": 1,
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "manifest": file_receipt(path),
        "mode_count": len(modes),
        "ordered_key_sha256": key_sha,
        "target_mode_physical_identity": physical,
        "original_size_ordered_mode_inventory_identity": inventory,
        "git_sources": files,
        "frozen_named_function_exports": {
            "dtn_port_3d": [
                "_outward_normal",
                "_mode_boundary_z",
                "_mode_boundary_phase",
                "_mode_projection_denominator",
                "_traction_vector",
            ],
            "target_runner": ["_target_config", "_target_mode_physical_identity"],
        },
        "historical_ledger_recovered": False,
        "PDE_solved": False,
        "FE_actions": 0,
        "factor_or_solve": 0,
        "NN_used": False,
        "official_results": False,
    }
    atomic_json(Path(binding["run_path"]) / "recovery_candidate.json", result)
    return result
