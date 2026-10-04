"""Saved full-vector audit, independent of the production cell application."""

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays


def canonical_outputs(packets, label):
    by = {k: [] for k in ("entity1", "entity2", "internal")}
    for p in packets:
        a = read_arrays(p["numeric"])
        for d in (1, 2):
            by[f"entity{d}"].append(
                (a[f"{label}_entity{d}_keys"], a[f"{label}_entity{d}"])
            )
        by["internal"].append((a["cell_keys"], a[label + "_internal"]))
    result = {}
    for name, pairs in by.items():
        keys = np.concatenate([p[0] for p in pairs])
        values = np.concatenate([p[1] for p in pairs])
        order = np.lexsort(keys[:, ::-1].T[::-1])
        keys, values = keys[order], values[order]
        if len(np.unique(keys, axis=0)) != len(keys):
            raise ValueError("duplicate full canonical output " + name)
        result[name] = (keys, values)
    return result


def compare_mpi(reference, packets, label):
    a, b = canonical_outputs(reference, label), canonical_outputs(packets, label)
    checks = []
    for name, (keys, values) in a.items():
        if not np.array_equal(keys, b[name][0]):
            raise ValueError("missing canonical full output " + name)
        checks.append(dict(kind=label + "_" + name, **metric(values, b[name][1])))
    return checks
