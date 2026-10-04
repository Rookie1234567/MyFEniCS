"""Literal saved geometry and native-kernel audits; no production apply."""

from collections import Counter, defaultdict
from time import perf_counter

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays
from benchmarks.check_native_entities import ranks, selected_arrays


def class_key(row, oriented=False):
    raw = (int(row["tag"]), *row["width_hex"])
    return (
        (raw + (int(row["permutation"]), tuple(row["native_reference_vertex_order"])))
        if oriented
        else raw
    )


def literal_class_counts(a, n):
    """Derive keys independently from coordinates, material and native codes."""
    raw, oriented = Counter(), Counter()
    local_keys = []
    for lo in range(0, n, 4096):
        xyz = a["coordinates"][a["cell_vertices"][lo : min(lo + 4096, n)]]
        low, high = xyz.min(axis=1), xyz.max(axis=1)
        mid = (low + high) / 2
        tags = np.ones(len(xyz), np.int32)
        tags[mid[:, 2] < 0] = 2
        inside = (
            (mid[:, 0] >= 16.5)
            & (mid[:, 0] <= 33.5)
            & (mid[:, 1] >= 0)
            & (mid[:, 1] <= 25)
            & (mid[:, 2] >= 0)
            & (mid[:, 2] <= 120)
        )
        tags[inside] = 3
        if not np.array_equal(tags, a["cell_tags"][lo : lo + len(xyz)]):
            raise ValueError("literal original three-tag identity")
        order = np.sum((xyz == high[:, None, :]) * np.array([1, 2, 4]), axis=2)
        if not np.all(np.sort(order, axis=1) == np.arange(8)):
            raise ValueError("native reference vertex order")
        for j, width in enumerate(high - low):
            key = (int(tags[j]), *[float(v).hex() for v in width])
            raw[key] += 1
            oriented[key + (int(a["cell_permutations"][lo + j]), tuple(order[j]))] += 1
            local_keys.append(key)
    return raw, oriented, local_keys


def require_declared_counts(counts, rows, *, oriented=False, users=None):
    keys = [class_key(r, oriented) for r in rows]
    if len(set(keys)) != len(keys) or counts != Counter(
        {k: r["count"] for k, r in zip(keys, rows, strict=True)}
    ):
        raise ValueError("raw/oriented exact class counts")
    if users is not None:
        for k, r in zip(keys, rows, strict=True):
            if sorted(users[k]) != r.get("rank_users"):
                raise ValueError("raw/oriented actual rank users")


def check_saved_target_classes(topology):
    """Read only bounded geometric operands, not feature/solve arrays."""
    began = perf_counter()
    packets = topology["packets"]
    ranks(packets, 2)
    counts = [Counter(), Counter()]
    users = [defaultdict(set), defaultdict(set)]
    rank_counts = []
    for packet in packets:
        meta = packet["metadata"]
        n = meta["entity_sizes"]["3"]["owned"]
        a = selected_arrays(
            packet["numeric"],
            [
                "coordinates",
                "cell_vertices",
                "cell_tags",
                "cell_permutations",
                "cell_raw_class_local",
            ],
        )
        raw, oriented, keys = literal_class_counts(a, n)
        declared = meta["raw_classes"]
        if any(
            key != class_key(declared[int(i)])
            for key, i in zip(keys, a["cell_raw_class_local"], strict=True)
        ):
            raise ValueError("per-cell exact raw class index")
        for j, (counter, rows) in enumerate(
            ((raw, declared), (oriented, meta["oriented_classes"]))
        ):
            require_declared_counts(counter, rows, oriented=bool(j))
            counts[j].update(counter)
            for key in counter:
                users[j][key].add(packet["rank"])
        rank_counts.append(
            {
                "rank": packet["rank"],
                "cells": n,
                "raw": len(raw),
                "oriented": len(oriented),
            }
        )
        del a, keys
    for j, name in enumerate(("raw_classes", "oriented_classes")):
        require_declared_counts(
            counts[j], topology[name], oriented=bool(j), users=users[j]
        )
    if (
        len(counts[0]) != 270
        or len(counts[1]) != 858
        or sum(counts[0].values()) != 530856
    ):
        raise ValueError("original-size exact class/cell inventory")
    return {
        "passed": True,
        "checks": [{"kind": "literal_raw_oriented_rank_users", "passed": True}],
        "raw": len(counts[0]),
        "oriented": len(counts[1]),
        "cells": sum(counts[0].values()),
        "rank_counts": rank_counts,
        "rank_private_raw": sum(map(len, users[0].values())),
        "rank_private_oriented": sum(map(len, users[1].values())),
        "seconds": perf_counter() - began,
        "new_matrices": 0,
        "new_factorizations": 0,
    }


def audit_internal_recovery():
    """Keep numerical negatives; quantify cancellation with immutable native tensors."""
    import basix
    from scipy.linalg.lapack import get_lapack_funcs

    from src.solvers.distributed_volume_scope import stage
    from src.solvers.distributed_volume_study import store
    from src.solvers.native_recovery_study import orient_basix_tensor

    began = perf_counter()
    s = store()
    element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        6,
        basix.LagrangeVariant.legendre,
    )
    ip = np.asarray(element.entity_dofs[3][0])
    tp = np.setdiff1d(np.arange(882), ip)
    native, factors, factor_checks = [], [], []
    for i in range(6):
        a = s.read(f"class_{i}_native")[1]["raw_native"]
        original = s.read(f"class_{i}_tensor")[1]["raw"]
        lu = s.read(f"class_{i}_lu")[1]["lu"]
        ii = np.ascontiguousarray(original[np.ix_(ip, ip)])
        rcond, info = get_lapack_funcs("gecon", (lu,))(lu, float(np.linalg.norm(ii, 1)))
        native.append(a)
        factors.append(
            {
                "class": i,
                "rows": 450,
                "rcond1_estimate": float(rcond),
                "info": int(info),
                "factor_reused": True,
                "new_factorization": False,
            }
        )
        factor_checks.append(
            dict(
                kind=f"class{i}_native_internal_tensor", **metric(ii, a[np.ix_(ip, ip)])
            )
        )
    records, checks = [], list(factor_checks)
    for n in (1, 2, 4):
        row, _ = stage("VOLUME" + str(n))
        for packet in row["packets"]:
            saved = read_arrays(packet["numeric"])
            literal = selected_arrays(
                packet["metadata"]["parent"], ["cell_permutations"]
            )
            for c, (u, f) in enumerate(
                zip(saved["recovered"], saved["fi"], strict=True)
            ):
                i = int(packet["metadata"]["class_ids"][c])
                a = orient_basix_tensor(
                    element, native[i], int(literal["cell_permutations"][c])
                )
                trace_term = a[np.ix_(ip, tp)] @ u[tp]
                interior_term = a[np.ix_(ip, ip)] @ u[ip]
                balance = (a @ u)[ip]
                m = metric(balance, f)
                check = dict(
                    kind=f"MPI{n}_rank{packet['rank']}_native_internal_cell{c}", **m
                )
                checks.append(check)
                records.append(
                    {
                        "MPI_size": n,
                        "rank": packet["rank"],
                        "cell_local": c,
                        "class": i,
                        "field_norm": float(np.linalg.norm(u)),
                        "rhs_norm": float(np.linalg.norm(f)),
                        "trace_term_norm": float(np.linalg.norm(trace_term)),
                        "interior_term_norm": float(np.linalg.norm(interior_term)),
                        "cancellation_ratio": float(
                            (np.linalg.norm(trace_term) + np.linalg.norm(interior_term))
                            / np.linalg.norm(f)
                        ),
                        "original_saved_balance": metric(
                            saved["internal_balance"][c], f
                        ),
                        "independent_native_balance": m,
                    }
                )
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "records": records,
        "class_condition_estimates": factors,
        "new_LU": 0,
        "new_recovery": 0,
        "seconds": perf_counter() - began,
        "interpretation": "operation-scale and existing-factor condition diagnostics only; not a universal error bound or a repaired solution",
    }
