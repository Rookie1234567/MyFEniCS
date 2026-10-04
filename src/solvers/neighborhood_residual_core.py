"""All-coefficient pilot: literal complete entities, original CSR, fixed GMRES.

No recovery, factor, global dense operator, teacher or learned online PC.
"""

from inspect import signature
from time import perf_counter

import numpy as np

from src.solvers.isolated_ml_sparse import LinearOperator, coo_matrix, csr_matrix, gmres


def ratio(actual, expected, tol=1e-10):
    num = float(np.linalg.norm(actual - expected))
    den = float(np.linalg.norm(expected))
    return {
        "numerator": num,
        "denominator": den,
        "relative": num / den if den else None,
        "passed": num <= tol * den if den else num == 0.0,
    }


def entity_graph(literal, metadata, interior_positions, transform):
    """Unique master nodes; a sparse orientation decoder, never row embeddings."""
    n = int(metadata["owned_dofs"])
    rows, cols, vals, node_keys, native_rows, sizes = [], [], [], [], [], []
    offsets, node_map, offset = [0], {}, 0
    for d, m in ((1, 6), (2, 60)):
        for j, gid in enumerate(literal[f"entity{d}_native_ids"]):
            if gid != literal[f"entity{d}_master_ids"][j]:
                continue
            key = tuple(map(int, literal[f"entity{d}_keys"][j]))
            node_map[d, int(gid)] = len(node_keys)
            node_keys.append(key)
            ids = literal[f"entity{d}_native_dofs"][j]
            t = transform(d, literal[f"entity{d}_vertex_permutations"][j])
            rr, cc = np.nonzero(t)
            rows.extend(ids[rr])
            cols.extend(offset + cc)
            vals.extend(t[rr, cc])
            native_rows.append(ids)
            sizes.append(m)
            offset += m
            offsets.append(offset)
    edge_face_nodes = len(node_keys)
    xyz, axes = literal["coordinates"], [np.asarray(x) for x in metadata["axes_nm"]]
    for c, cell in enumerate(literal["cell_vertices"]):
        low = xyz[cell].min(axis=0)
        key = (3, 3, *[int(np.searchsorted(axes[a], low[a])) for a in range(3)])
        node_keys.append(key)
        ids = literal["cell_native_dofs"][c, interior_positions]
        rows.extend(ids)
        cols.extend(offset + np.arange(450))
        vals.extend(np.ones(450, complex))
        native_rows.append(ids)
        sizes.append(450)
        offset += 450
        offsets.append(offset)
    bridge = coo_matrix(
        (vals, (rows, cols)), shape=(n, offset), dtype=np.complex128
    ).tocsr()
    bridge.sum_duplicates()
    independent = np.setdiff1d(np.arange(n), literal["slave_local_dofs"])
    coverage = np.concatenate(native_rows)
    if (
        len(coverage) != offset
        or len(np.unique(coverage)) != offset
        or not np.array_equal(np.sort(coverage), independent)
    ):
        raise ValueError(
            "all independent trace/interior coefficients must appear exactly once"
        )
    links = set()
    for c in range(len(literal["cell_vertices"])):
        cell_node = edge_face_nodes + c
        for d in (1, 2):
            for j in literal[f"cell_entity{d}"][c]:
                neighbor = node_map[d, int(literal[f"entity{d}_master_ids"][j])]
                links.add((cell_node, neighbor))
                links.add((neighbor, cell_node))
    src, dst = np.asarray(sorted(links), np.int64).T
    degree = np.bincount(dst, minlength=len(node_keys))
    if np.any(degree == 0):
        raise ValueError("every complete entity needs an actual cell neighbor")
    centers = []
    for key in node_keys:
        d, direction, *idx = key
        center = [axes[a][idx[a]] for a in range(3)]
        for a in range(3):
            if d == 3 or (d == 1 and direction == a) or (d == 2 and direction != a):
                center[a] = (axes[a][idx[a]] + axes[a][idx[a] + 1]) / 2
        centers.append(center)
    return bridge, {
        "offsets": np.asarray(offsets),
        "sizes": np.asarray(sizes),
        "keys": np.asarray(node_keys),
        "src": src,
        "dst": dst,
        "degree": degree,
        "centers": np.asarray(centers),
        "independent": independent,
        "slaves": literal["slave_local_dofs"],
        "shape": np.asarray(bridge.shape),
    }


class OriginalCSR:
    """One original matrix plus explicit conjugate-data adjoint; all copies costed."""

    def __init__(self, arrays, budget=None):
        self.matrix = csr_matrix(
            (arrays["data"], arrays["indices"], arrays["indptr"]),
            shape=tuple(arrays["shape"]),
            copy=False,
        )
        self.adjoint = self.matrix.conjugate().transpose(copy=False)
        self.budget = budget
        diag = self.matrix.diagonal()
        self.zero_diagonal = np.flatnonzero(diag == 0)
        self.scale = np.ones_like(diag)
        nonzero = diag != 0
        self.scale[nonzero] = 1 / diag[nonzero]
        if not np.isfinite(self.scale).all():
            raise ArithmeticError("nonfinite original right diagonal")
        self.calls = {"A": 0, "AH": 0}
        self.seconds = dict.fromkeys(self.calls, 0.0)

    def apply(self, x, *, adjoint=False):
        x = np.asarray(x, np.complex128)
        kind = "AH" if adjoint else "A"
        began = perf_counter()
        fun = (self.adjoint if adjoint else self.matrix).__matmul__
        out = self.budget.call(fun, x, kind=kind) if self.budget else fun(x)
        self.calls[kind] += 1 if x.ndim == 1 else x.shape[1]
        self.seconds[kind] += perf_counter() - began
        return out


def fixed_cleanup(action, rhs, initial, *, restart=32, max_steps=128, tol=1e-6):
    """Right diagonal GMRES with committed, bounded restart boundaries.

    The qualified SciPy driver does not return the pending partial update when
    a legacy callback interrupts a restart. One complete boundary call at a
    time preserves the actual update, with at most 128 total Arnoldi steps.
    """
    rhs = np.asarray(rhs, np.complex128)
    initial = np.asarray(initial, np.complex128)
    norm = float(np.linalg.norm(rhs))
    began = perf_counter()
    if norm == 0:
        z = np.zeros_like(rhs)
        return z, {
            "steps": 0,
            "info": 0,
            "history": [],
            "rho": 0.0,
            "seconds": perf_counter() - began,
        }
    residual = rhs - action.apply(initial)
    if np.linalg.norm(residual) <= tol * norm:
        return initial.copy(), {
            "steps": 0,
            "info": 0,
            "history": [],
            "rho": float(np.linalg.norm(residual) / norm),
            "seconds": perf_counter() - began,
        }
    count = action.calls.copy()
    history = []
    operator = LinearOperator(
        (len(rhs), len(rhs)),
        matvec=lambda y: action.apply(action.scale * y),
        dtype=np.complex128,
    )
    y, info = np.zeros_like(rhs), 1
    boundaries = []
    while len(history) < max_steps:
        remaining = max_steps - len(history)
        before = len(history)
        y, info = gmres(
            operator,
            residual,
            x0=y,
            M=None,
            restart=min(restart, remaining),
            maxiter=1,
            atol=tol * norm,
            callback=lambda value: history.append(float(value)),
            callback_type="pr_norm",
            **(
                {"rtol": 0.0} if "rtol" in signature(gmres).parameters else {"tol": 0.0}
            ),
        )
        boundaries.append({"steps": len(history), "info": int(info)})
        if len(history) - before > min(restart, remaining):
            raise RuntimeError("qualified GMRES inner count exceeds fixed cap")
        if info == 0 or len(history) == before:
            break
    z = initial + action.scale * y
    actual = rhs - action.apply(z)
    return z, {
        "steps": len(history),
        "info": int(info),
        "history": history,
        "rho": float(np.linalg.norm(actual) / norm),
        "seconds": perf_counter() - began,
        "A_calls": action.calls["A"] - count["A"],
        "Arnoldi_cap": max_steps,
        "right_preconditioner": "frozen original diagonal",
        "callback_type": "pr_norm",
        "maxiter_semantics": "one complete restart boundary per SciPy call",
        "boundaries": boundaries,
        "explicit_residual_norm": float(np.linalg.norm(actual)),
        "rhs_norm": norm,
    }


def manufactured(graph, family, seed):
    """Fixed independent families; sealed errors never enter the training reader."""
    rng = np.random.default_rng(seed)
    offsets, centers, sizes = graph["offsets"], graph["centers"], graph["sizes"]
    values = np.zeros(int(offsets[-1]), np.complex128)
    span = np.ptp(centers, axis=0)
    position = (centers - centers.min(axis=0)) / span
    anchor = rng.uniform(0.15, 0.85, 3)
    phase = rng.uniform(-np.pi, np.pi)
    freq = rng.uniform(0.4, 1.2, 3)
    for i, m in enumerate(sizes):
        ids = slice(int(offsets[i]), int(offsets[i + 1]))
        if family.startswith("local_"):
            if np.max(abs(position[i] - anchor)) > 0.36:
                continue
            distribution = family.removeprefix("local_")
            draw = (
                rng.normal
                if distribution == "gaussian"
                else (
                    rng.laplace
                    if distribution == "laplace"
                    else lambda size: rng.uniform(-1, 1, size)
                )
            )
            values[ids] = draw(size=m) + 1j * draw(size=m)
        else:
            q = float(position[i] @ freq)
            amplitude = np.cos(q + phase) + 1j * np.sin(0.7 * q - phase)
            if family == "cross_sine":
                amplitude = np.sin(q + phase) + 1j * np.cos(0.8 * q - phase)
            elif family == "cross_mixed_smooth":
                amplitude = (1 + q / 4) * (
                    np.cos(0.3 * q + phase) + 1j * np.sin(0.4 * q - phase)
                )
            values[ids] = amplitude / (1 + np.arange(m))
    values /= np.linalg.norm(values)
    return values
