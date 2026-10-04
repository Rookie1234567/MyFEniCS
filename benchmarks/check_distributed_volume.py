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
        order = np.lexsort(keys.T[::-1])
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


def check_recovery():
    """Reassemble saved owned arrays and audit against the original CSR."""
    from scipy.sparse import csr_matrix

    from src.solvers.distributed_recovery_study import producer_store
    from src.solvers.distributed_volume_scope import stage

    s, _ = producer_store()
    _, saved = s.read("recovery")
    _, sparse = s.read("oracle")
    _, literal = s.read("geometry")
    matrix = csr_matrix(
        (sparse["data"], sparse["indices"], sparse["indptr"]),
        shape=tuple(sparse["shape"]),
    )
    C, D = saved["C_native"], saved["D_native"]
    checks = []
    for n in (2, 4):
        result, _ = stage("RECOVERY" + str(n))
        packets = result["packets"]
        if (
            result["MPI_size"] != n
            or len(packets) != n
            or sorted(p["rank"] for p in packets) != list(range(n))
        ):
            raise ValueError("complete actual recovery rank inventory")
        joined, coverage = {}, np.zeros(matrix.shape[0], np.int32)
        for p in packets:
            a = read_arrays(p["numeric"])
            own = a["producer_owned_ids"]
            if len(np.unique(own)) != len(own) or np.any(
                a["producer_row_owners"][own] != p["rank"]
            ):
                raise ValueError("recovery actual owner identity")
            np.add.at(coverage, own, 1)
            for name in (
                "u",
                "u2",
                "u_difference",
                "u_zero",
                "rFE",
                "rnative",
                "native_coupled_u",
            ):
                joined.setdefault(name, np.empty(matrix.shape[0], np.complex128))[
                    own
                ] = a[name]
            for label in ("a", "b", "zero", "scale"):
                for suffix in ("x", "volume", "adjoint_volume", "action", "adjoint"):
                    name = label + "_" + suffix
                    joined.setdefault(name, np.empty(matrix.shape[0], np.complex128))[
                        own
                    ] = a[name]
            size = int(a["current_owned_size"][0])
            checks.extend(
                [
                    dict(
                        kind=f"MPI{n}_rank{p['rank']}_native_MPC",
                        **metric(
                            a["native_expanded"][:size], a["native_expected"][:size]
                        ),
                    ),
                    dict(
                        kind=f"MPI{n}_rank{p['rank']}_reduced_rhs",
                        **metric(a["reduced_rhs"], saved["reduced_rhs"]),
                    ),
                    dict(
                        kind=f"MPI{n}_rank{p['rank']}_complete_port",
                        **metric(
                            a["rport"], saved["g"] + D @ saved["u"] - saved["alpha"]
                        ),
                    ),
                ]
            )
            if np.any(a["native_computation"][a["native_slaves"]]):
                raise ValueError("actual recovery computation slave zero")
        if not np.all(coverage == 1):
            raise ValueError("complete recovery owned rows exactly once")
        for label in ("a", "b", "zero", "scale"):
            x = joined[label + "_x"]
            if not np.array_equal(x, saved[label + "_x"]) or np.any(
                x[literal["slaves"]]
            ):
                raise ValueError("fixed full complex input/slave inventory")
            for suffix, expected in (
                ("volume", matrix @ x),
                ("adjoint_volume", matrix.conjugate().T @ x),
                ("action", matrix @ x + C @ (D @ x)),
                (
                    "adjoint",
                    matrix.conjugate().T @ x + D.conjugate().T @ (C.conjugate().T @ x),
                ),
            ):
                checks.append(
                    dict(
                        kind=f"MPI{n}_CSR_{label}_{suffix}",
                        **metric(joined[label + "_" + suffix], expected),
                    )
                )
        for name in ("u", "u2", "u_difference", "u_zero"):
            checks.append(
                dict(kind=f"MPI{n}_affine_{name}", **metric(joined[name], saved[name]))
            )
        u = joined["u"]
        checks.extend(
            [
                dict(
                    kind=f"MPI{n}_homogeneous",
                    **metric(
                        u - joined["u2"], joined["u_difference"] - joined["u_zero"]
                    ),
                ),
                dict(
                    kind=f"MPI{n}_augmented_FE",
                    **metric(
                        joined["rFE"], saved["f"] - matrix @ u - C @ saved["alpha"]
                    ),
                ),
                dict(
                    kind=f"MPI{n}_native_identity",
                    **metric(
                        joined["rnative"],
                        joined["rFE"] - C @ (saved["g"] + D @ u - saved["alpha"]),
                    ),
                ),
                dict(
                    kind=f"MPI{n}_coupled_recovered",
                    **metric(joined["native_coupled_u"], matrix @ u + C @ (D @ u)),
                ),
            ]
        )
    return {
        "passed": bool(checks) and all(c["passed"] for c in checks),
        "checks": checks,
        "oracle": "immutable original V40 CSR/C/D/f/g; all owned rows reconstructed exactly once",
        "PDE_solved": False,
        "producer_MPI": 1,
        "consumer_MPI": [2, 4],
    }
