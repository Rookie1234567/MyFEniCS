"""Independent V41 literal inventory/vector checker, no solver or FE runtime."""

import numpy as np

from benchmarks.check_boundary_witness import metric, read_arrays


def ranks(records, expected):
    found = [r["rank"] for r in records]
    if sorted(found) != list(range(expected)) or any(
        r["MPI_size"] != expected or not r["commit"] for r in records
    ):
        raise ValueError("complete actual MPI rank inventory")


def check_packets(records, *, fixture=False):
    if not records:
        raise ValueError("empty actual rank inventory")
    ranks(records, records[0]["MPI_size"])
    checks, owner_parts = [], {1: [], 2: []}
    data = [read_arrays(r["numeric"]) for r in records]
    for record, a in zip(records, data, strict=True):
        rank = record["rank"]
        for d, n in ((1, 6), (2, 60)):
            size = record["metadata"]["entity_sizes"][str(d)]
            owned = size["owned"]
            keys = a[f"entity{d}_keys"]
            if keys.shape != (owned + size["ghost"], 5) or len(
                np.unique(keys, axis=0)
            ) != len(keys):
                raise ValueError("complete literal local entity inventory")
            if np.any(a[f"entity{d}_owners"][:owned] != rank):
                raise ValueError("wrong actual native owner")
            owner_parts[d].append(
                np.column_stack(
                    (
                        keys[:owned],
                        a[f"entity{d}_native_ids"][:owned],
                        np.full(owned, rank, np.int64),
                    )
                )
            )
            if fixture and a[f"entity{d}_physical"].shape != (len(keys), n):
                raise ValueError("complete high order entity moments")
            shape = record["metadata"]["axis_cells"]
            phases = [complex(*p) for p in record["metadata"]["phases"]]
            expected_master = keys.copy()
            expected_phase = np.ones(len(keys), np.complex128)
            for axis in (0, 1):
                on = (keys[:, 2 + axis] == shape[axis]) & (
                    (d == 2) | (keys[:, 1] != axis)
                )
                expected_master[on, 2 + axis] = 0
                expected_phase[on] *= phases[axis]
            if not np.array_equal(expected_master, a[f"entity{d}_master_keys"]):
                raise ValueError("wrong literal periodic master")
            checks.append(
                {
                    "kind": f"phase_dim{d}_rank{rank}",
                    **metric(expected_phase, a[f"entity{d}_phase"]),
                }
            )
        if fixture:
            nn = record["metadata"]["original_function_local_rows"]
            if not np.all(a["dof_coverage"] == 1) or np.any(
                a["computation"][a["slave_local_dofs"]]
            ):
                raise ValueError("actual native coverage/slave zero")
            checks.append(
                {
                    "kind": "complete_native_MPC_rank" + str(rank),
                    **metric(a["expanded_native"][:nn], a["independent_physical"]),
                }
            )
            # Recompute the native MPC expansion directly from saved literal
            # coefficients, including nonlocal masters already in the vector.
            pred = a["computation"].copy()
            for slave in a["slave_local_dofs"]:
                lo, hi = a["MPC_offsets"][slave : slave + 2]
                pred[slave] = np.dot(
                    a["MPC_coefficients"][lo:hi],
                    a["computation"][a["MPC_masters"][lo:hi]],
                )
            checks.append(
                {
                    "kind": "literal_MPC_rank" + str(rank),
                    **metric(pred, a["expanded_native"]),
                }
            )
            checks.append(
                {
                    "kind": "native_complex_scale_rank" + str(rank),
                    **metric(
                        a["scaled_expanded"], (0.37 - 0.91j) * a["expanded_native"]
                    ),
                }
            )
            if np.any(a["zero_expanded"]):
                raise ValueError("actual zero native witness is nonzero")
    counts = {}
    for d in (1, 2):
        # Compact integer sort/search, no global Python entity/moment dictionary.
        all_owned = np.concatenate(owner_parts[d])
        void = np.dtype((np.void, 5 * 8))
        keys = np.ascontiguousarray(all_owned[:, :5]).view(void).ravel()
        order = np.argsort(keys)
        sorted_keys = keys[order]
        if np.any(sorted_keys[1:] == sorted_keys[:-1]):
            raise ValueError("duplicate globally owned entity")
        counts[d] = len(all_owned)
        for record, a in zip(records, data, strict=True):
            requested = (
                np.ascontiguousarray(a[f"entity{d}_master_keys"]).view(void).ravel()
            )
            index = np.searchsorted(sorted_keys, requested)
            if np.any(index >= len(sorted_keys)) or not np.array_equal(
                sorted_keys[index], requested
            ):
                raise ValueError("missing actual periodic master")
            bound = all_owned[order[index], 5:]
            if not np.array_equal(
                bound[:, 0], a[f"entity{d}_master_ids"]
            ) or not np.array_equal(bound[:, 1], a[f"entity{d}_master_owners"]):
                raise ValueError("periodic master key/native owner mismatch")
        if counts[d] != records[0]["metadata"]["entity_sizes"][str(d)]["global"]:
            raise ValueError("global entity coverage")
        del all_owned, keys, order, sorted_keys
    if not fixture:
        expected_cell_count = int(np.prod(records[0]["metadata"]["axis_cells"]))
        native_cells = []
        global_raw = {}
        boundary_count = 0
        for record, a in zip(records, data, strict=True):
            n = record["metadata"]["entity_sizes"]["3"]["owned"]
            native_cells.append(a["cell_native_ids"][:n])
            if a["cell_tags"].shape != (n,):
                raise ValueError("complete owned-cell material inventory")
            rows = record["metadata"]["raw_classes"]
            class_counts = np.bincount(a["cell_raw_class_local"], minlength=len(rows))
            if len(class_counts) != len(rows) or not np.array_equal(
                class_counts, [r["count"] for r in rows]
            ):
                raise ValueError("raw class exact consumption inventory")
            for lo in range(0, n, 4096):
                xyz = a["coordinates"][a["cell_vertices"][lo : min(lo + 4096, n)]]
                low, high = xyz.min(axis=1), xyz.max(axis=1)
                mid = (low + high) / 2
                tags = np.ones(len(xyz), np.int32)
                tags[mid[:, 2] < 0] = 2
                inside = (
                    (mid[:, 0] >= 16.5)
                    & (mid[:, 0] <= 33.5)
                    & (mid[:, 2] >= 0)
                    & (mid[:, 2] <= 120)
                )
                tags[inside] = 3
                if not np.array_equal(tags, a["cell_tags"][lo : lo + len(xyz)]):
                    raise ValueError("independent original-size three-tag geometry")
                for i, widths in enumerate(high - low):
                    index = int(a["cell_raw_class_local"][lo + i])
                    key = (int(tags[i]), *[float(w).hex() for w in widths])
                    declared = rows[index]
                    if key != (declared["tag"], *declared["width_hex"]):
                        raise ValueError("exact raw float class mismatch")
                    global_raw[key] = global_raw.get(key, 0) + 1
            faces = a["entity2_keys"]
            nf = record["metadata"]["entity_sizes"]["2"]["owned"]
            shape = np.array(record["metadata"]["axis_cells"])
            axis = faces[:nf, 1]
            coordinate = faces[:nf, 2:][np.arange(nf), axis]
            expected_boundary = np.flatnonzero(
                (coordinate == 0) | (coordinate == shape[axis])
            )
            actual_boundary = a["boundary_facets"][a["boundary_facets"] < nf]
            if not np.array_equal(np.sort(actual_boundary), expected_boundary):
                raise ValueError("actual native exterior-face coverage")
            boundary_count += len(actual_boundary)
        cells = np.concatenate(native_cells)
        if len(cells) != expected_cell_count or not np.array_equal(
            np.sort(cells), np.arange(expected_cell_count)
        ):
            raise ValueError("complete actual target owned-cell ID inventory")
        checks.append(
            {
                "kind": "actual_target_cells_raw_material_boundary",
                "passed": True,
                "cells": len(cells),
                "raw_classes": len(global_raw),
                "exterior_faces": boundary_count,
            }
        )
    if fixture:
        total = records[0]["metadata"]["actual_p6_global_rows"]
        primal = np.zeros(total, np.complex128)
        expanded = np.zeros(total, np.complex128)
        dual = np.zeros(total, np.complex128)
        owned_coverage = np.zeros(total, np.int8)
        predicted_pull = np.zeros(total, np.complex128)
        for record, a in zip(records, data, strict=True):
            n = record["metadata"]["owned_dofs"]
            gid = a["actual_dof_global_ids"][:n]
            np.add.at(owned_coverage, gid, 1)
            primal[gid] = a["computation"][:n]
            expanded[gid] = a["expanded_native"][:n]
            dual[gid] = a["native_dual"][:n]
            slaves = set(map(int, a["slave_local_dofs"]))
            for row in range(n):
                if row in slaves:
                    lo, hi = a["MPC_offsets"][row : row + 2]
                    masters = a["actual_dof_global_ids"][a["MPC_masters"][lo:hi]]
                    np.add.at(
                        predicted_pull,
                        masters,
                        a["MPC_coefficients"][lo:hi].conjugate()
                        * a["native_dual"][row],
                    )
                else:
                    predicted_pull[gid[row]] += a["native_dual"][row]
            for d, moments in ((1, 6), (2, 60)):
                count = record["metadata"]["entity_sizes"][str(d)]["owned"]
                keys = a[f"entity{d}_keys"][:count].astype(np.float64)
                k = keys @ np.array([1.17, 0.31, 0.73, 0.19, 0.47])
                j = np.arange(moments)[None, :]
                values = np.sin(k[:, None] + j * 0.37 + 424101 * 0.013) + 1j * np.cos(
                    k[:, None] * 0.83 + j * 0.61 + 424101 * 0.017
                )
                checks.append(
                    {
                        "kind": f"MPI_invariant_seed_dim{d}_rank{record['rank']}",
                        **metric(values, a[f"entity{d}_owned_canonical"]),
                    }
                )
        if not np.all(owned_coverage == 1):
            raise ValueError("full finite native owned row coverage")
        for record, a in zip(records, data, strict=True):
            n = record["metadata"]["owned_dofs"]
            gid = a["actual_dof_global_ids"][:n]
            checks.append(
                {
                    "kind": "independent_global_MPC_dual_rank" + str(record["rank"]),
                    **metric(predicted_pull[gid], a["literal_dual_scatter"][:n]),
                }
            )
        checks.append(
            {
                "kind": "independent_full_native_duality",
                **metric(
                    np.array([np.vdot(dual, expanded)]),
                    np.array([np.vdot(predicted_pull, primal)]),
                ),
            }
        )
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "global_owned_edges": counts[1],
        "global_owned_faces": counts[2],
    }


def check_directions(receipt):
    a = read_arrays(receipt)
    raw, codes = a["raw"], a["codes"]
    if raw.shape != (882, 882) or raw.dtype != np.complex128 or not len(codes):
        raise ValueError("complete saved native p6 direction inventory")
    checks = []
    edge, face = a["interval_transform"][0], a["quadrilateral_transform"]
    for value in codes:
        code = int(value)
        out = raw.copy()
        blocks = []
        # Basix N1E p6: 12 consecutive six-row edge blocks, then six
        # sixty-row face blocks, then 450 interiors. Literal p6 generators.
        for i in range(12):
            if (code >> (18 + i)) & 1:
                blocks.append((slice(i * 6, (i + 1) * 6), edge))
        for i in range(6):
            bits = (code >> (i * 3)) & 7
            transform = np.eye(60)
            if bits & 1:
                transform = face[1] @ transform
            for _ in range(bits // 2):
                transform = face[0] @ transform
            blocks.append((slice(72 + i * 60, 72 + (i + 1) * 60), transform))
        for rows, transform in blocks:
            out[rows, :] = transform @ out[rows, :]
        for rows, transform in blocks:
            out[:, rows] = out[:, rows] @ transform.T
        checks.append(
            {
                "kind": "independent_two_axis_" + str(code),
                **metric(out, a["native_" + str(code)]),
            }
        )
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def check_routing(packets, rows=378432):
    ranks(packets, 2)
    coverage = np.zeros(rows, np.int8)
    checks = []
    for p in packets:
        a = read_arrays(p["numeric"])
        for d in (1, 2):
            ids = a[f"boundary{d}_canonical_rows"]
            if ids.ndim != 2 or np.any(ids < 0) or np.any(ids >= rows):
                raise ValueError("complete boundary row inventory")
            np.add.at(coverage, ids.ravel(), 1)
            checks.append(
                {
                    "kind": f"boundary{d}_owner_extract_rank{p['rank']}",
                    **metric(a[f"boundary{d}_extracted"], a[f"boundary{d}_expected"]),
                }
            )
        checks.append(
            {
                "kind": "complete_owner_duality_rank" + str(p["rank"]),
                **metric(a["global_duality_left"], a["global_duality_right"]),
            }
        )
    if not np.all(coverage == 1):
        raise ValueError("missing/duplicate full boundary entity/face moments")
    return {"passed": all(c["passed"] for c in checks), "checks": checks, "rows": rows}
