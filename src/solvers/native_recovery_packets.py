"""Immutable native checkpoints, including the actual local factors.

Payloads publish before a small commit manifest. An interrupted write never
replaces a prior stage. No pickle or status-only reader is accepted.
"""

import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

import numpy as np

from benchmarks.check_boundary_witness import read_arrays
from src.runners.task042_shared import write_json
from src.solvers.port_component_study import array_file


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PacketStore:
    def __init__(self, root, dependencies, *, expected_contract=None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.dependencies = dependencies
        self.expected_contract = expected_contract

    def save(self, name, arrays, metadata):
        path = self.root / (name + ".json")
        if path.exists():
            raise FileExistsError("immutable successful native packet " + name)
        began = perf_counter()
        receipt = array_file(
            self.root / (name + ".npz"), compressed=True, deduplicate=True, **arrays
        )
        row = {
            "schema": "native-recovery-packet.v1",
            "name": name,
            "arrays": receipt,
            "dependencies": self.dependencies,
            "source_sha": os.environ.get("TASK042_RUN_SOURCE"),
            "metadata": metadata,
            "save_hash_seconds": perf_counter() - began,
            "unique_payload_bytes": sum(
                np.asarray(arrays[k]).nbytes
                for k in arrays
                if k not in receipt["aliases"]
            ),
            "commit": True,
        }
        write_json(path, row)
        print(
            json.dumps(
                {
                    "checkpoint": name,
                    "manifest": str(path),
                    "sha256": sha(path),
                    "unique_payload_bytes": row["unique_payload_bytes"],
                }
            ),
            flush=True,
        )
        return row

    def read(self, name):
        row = json.loads((self.root / (name + ".json")).read_text())
        if (
            row.get("commit") is not True
            or row.get("name") != name
            or row["dependencies"] != self.dependencies
        ):
            raise ValueError("native packet dependency/commit identity")
        return row, read_arrays(row["arrays"])

    def has(self, name):
        if not (self.root / (name + ".json")).exists():
            return False
        self.read(name)
        return True


def save_system(store, system, class_names):
    """Small numbering packet points to class manifests; no factor recopy."""
    classes = list(system.retained_local_original_by_class)
    constraints = system.trace_constraints
    keys = sorted(constraints.expansion_by_original)
    ids = [constraints.expansion_by_original[k][0] for k in keys]
    vals = [constraints.expansion_by_original[k][1] for k in keys]
    arrays = {
        "owned_trace": system.owned_trace_original_dofs,
        "original_to_trace": np.array(
            sorted(system.original_to_trace.items()), np.int64
        ),
        "owned_active": constraints.owned_active_original_dofs,
        "original_to_active": np.array(
            sorted(constraints.original_to_active.items()), np.int64
        ),
        "expansion_original": np.array(keys, np.int64),
        "expansion_offsets": np.r_[0, np.cumsum([len(a) for a in ids])].astype(
            np.int64
        ),
        "expansion_ids": np.concatenate(ids),
        "expansion_coefficients": np.concatenate(vals),
        "cell_interior": np.array(
            [c.interior_original_dofs for c in system.cell_recovery_maps]
        ),
        "cell_trace": np.array(
            [c.trace_original_dofs for c in system.cell_recovery_maps]
        ),
        "cell_class": np.array(
            [classes.index(c.class_key) for c in system.cell_recovery_maps], np.int64
        ),
    }
    numeric_names = (
        "full_rows",
        "trace_rows",
        "active_rows",
        "appended_rows",
        "interior_rows",
        "active_interior_rows",
        "owned_active_rows",
        "owned_appended_rows",
    )
    return store.save(
        "system",
        arrays,
        {
            "sizes": {n: int(getattr(system, n)) for n in numeric_names},
            "constraint_sizes": {
                n: int(getattr(constraints, n))
                for n in ("full_trace_rows", "active_rows", "slave_rows")
            },
            "classes": [
                {"name": name, "sha256": sha(store.root / (name + ".json"))}
                for name in class_names
            ],
            "build_audit": system.build_audit,
            "constraint_audit": constraints.build_audit,
            "original_class_keys": list(map(repr, classes)),
        },
    )


def load_system(store):
    from mpi4py import MPI

    from src.solvers.hcurl_assembly_time_condensation import (
        AssemblyTimeCondensedSystem,
        CellRecoveryMap,
        TraceConstraintMap,
    )

    row, a = store.read("system")
    m = row["metadata"]
    class_arrays = []
    for item in m["classes"]:
        if sha(store.root / (item["name"] + ".json")) != item["sha256"]:
            raise ValueError("class checkpoint parent hash")
        class_arrays.append(store.read(item["name"])[1])
    keys = [("saved-class", i) for i in range(len(class_arrays))]
    exp = {}
    for i, original in enumerate(a["expansion_original"]):
        lo, hi = a["expansion_offsets"][i : i + 2]
        exp[int(original)] = (
            a["expansion_ids"][lo:hi],
            a["expansion_coefficients"][lo:hi],
        )
    constraints = TraceConstraintMap(
        a["owned_active"],
        dict(map(tuple, a["original_to_active"])),
        exp,
        **m["constraint_sizes"],
        build_audit=m["constraint_audit"],
    )

    def field(name):
        return {k: v[name] for k, v in zip(keys, class_arrays, strict=True)}

    system = AssemblyTimeCondensedSystem(
        matrix=None,
        owned_trace_original_dofs=a["owned_trace"],
        original_to_trace=dict(map(tuple, a["original_to_trace"])),
        trace_constraints=constraints,
        cell_recovery_maps=tuple(
            CellRecoveryMap(i, t, keys[int(c)])
            for i, t, c in zip(
                a["cell_interior"], a["cell_trace"], a["cell_class"], strict=True
            )
        ),
        interior_from_trace_by_class=field("recovery"),
        interior_lu_by_class={
            k: (v["lu"], v["pivots"]) for k, v in zip(keys, class_arrays, strict=True)
        },
        interior_rhs_projection_by_class=field("identity"),
        interior_solution_embedding_by_class=field("identity"),
        trace_from_interior_rhs_by_class=field("rhs_trace"),
        interior_residual_projection_by_class=field("identity"),
        retained_local_schur_by_class=field("schur"),
        retained_local_original_by_class=field("original"),
        comm=MPI.COMM_SELF,
        build_audit=m["build_audit"],
        **m["sizes"],
    )
    return system, class_arrays
