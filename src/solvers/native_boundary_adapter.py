"""Owner-local native primal extraction and conjugate dual scatter.

The sparse map is constructed from literal entity moments, native cell
orientation and finalized MPC expansion. It is never fitted to modal data.
Only MPI1 native witnesses are qualified; full-target volume row IDs are not
invented by this boundary component.
"""

from time import perf_counter

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix


def vector(value, size, name):
    a = np.asarray(value)
    if a.shape != (size,) or a.dtype != np.complex128 or not np.isfinite(a).all():
        raise ValueError(name + " shape/complex128/finite")
    return a


def literal_expansion(literal, n):
    offsets = literal.get("master_offsets", np.arange(n + 1))
    rows = literal.get("master_rows", np.arange(n))
    coeff = literal.get("master_dual_coefficients", np.ones(n, complex)).conj()
    if (
        offsets.shape != (n + 1,)
        or offsets[0] != 0
        or offsets[-1] != len(rows)
        or len(rows) != len(coeff)
        or np.any(np.diff(offsets) < 1)
    ):
        raise ValueError("literal complete MPC expansion inventory")
    if np.any(rows < 0) or np.any(rows >= n) or not np.isfinite(coeff).all():
        raise ValueError("literal MPC master index/finite")
    return csr_matrix((coeff, rows, offsets), shape=(n, n))


class NativeBoundaryAdapter:
    def __init__(
        self, E, compact_rows, native_size, boundary_size, slaves, *, identity
    ):
        self.E = csr_matrix(E, dtype=np.complex128, copy=True)
        self.E.sum_duplicates()
        self.E.sort_indices()
        self.compact_rows = np.array(compact_rows, dtype=np.int64, copy=True)
        self.slaves = np.array(slaves, dtype=np.int64, copy=True)
        self.native_size, self.boundary_size = native_size, boundary_size
        if (
            self.E.shape != (len(self.compact_rows), native_size)
            or len(np.unique(self.compact_rows)) != len(self.compact_rows)
            or np.any(self.compact_rows < 0)
            or np.any(self.compact_rows >= boundary_size)
            or not np.isfinite(self.E.data).all()
        ):
            raise ValueError("sparse native boundary row inventory")
        if (
            np.any(self.slaves < 0)
            or np.any(self.slaves >= native_size)
            or self.E[:, self.slaves].nnz
        ):
            raise ValueError("adapter independent storage contains slave columns")
        self.EH = self.E.conjugate().transpose().tocsr()
        for a in (
            self.E.data,
            self.E.indices,
            self.E.indptr,
            self.EH.data,
            self.EH.indices,
            self.EH.indptr,
            self.compact_rows,
            self.slaves,
        ):
            a.flags.writeable = False
        self.identity = str(identity)
        self.stats = {
            "extract_calls": 0,
            "scatter_calls": 0,
            "extract_seconds": 0.0,
            "scatter_seconds": 0.0,
        }

    def independent(self, value):
        a = vector(value, self.native_size, "native independent primal")
        if self.slaves.size and np.any(a[self.slaves] != 0):
            raise ValueError("native computation storage requires exact slave zero")
        return a

    def extract(self, value):
        began = perf_counter()
        a = self.independent(value)
        out = np.zeros(self.boundary_size, np.complex128)
        out[self.compact_rows] = self.E @ a
        self.stats["extract_calls"] += 1
        self.stats["extract_seconds"] += perf_counter() - began
        return out

    def scatter(self, value):
        began = perf_counter()
        a = vector(value, self.boundary_size, "boundary dual")
        out = self.EH @ a[self.compact_rows]
        self.stats["scatter_calls"] += 1
        self.stats["scatter_seconds"] += perf_counter() - began
        return out

    def arrays(self):
        return {
            "E_data": self.E.data,
            "E_indices": self.E.indices,
            "E_indptr": self.E.indptr,
            "compact_rows": self.compact_rows,
            "slaves": self.slaves,
            "sizes": np.array([self.native_size, self.boundary_size], np.int64),
        }

    @classmethod
    def from_arrays(cls, arrays, *, identity):
        n, nb = map(int, arrays["sizes"])
        E = csr_matrix(
            (arrays["E_data"], arrays["E_indices"], arrays["E_indptr"]),
            shape=(len(arrays["compact_rows"]), n),
        )
        return cls(
            E, arrays["compact_rows"], n, nb, arrays["slaves"], identity=identity
        )


def build_literal_adapter(element, literal, description, layout, n, slaves):
    """One complete entity owner, no shared-cell duplicate sum or global LS.

    Basis orientation is the native T applied to reference basis columns.
    Hence primal coefficients use T-transpose, followed by the primal MPC
    expansion and division by the physical slave-to-master boundary phase.
    The returned transpose scatter supplies all dual conjugations.
    """
    G = literal_expansion(literal, n)
    coefficients = {}
    ownership = []
    duplicates = []
    maximum_block = 0
    for cell, dofs in enumerate(literal["cell_dofs"]):
        coords = literal["coordinates"][literal["geometry_dofmap"][cell]]
        bounds = np.column_stack((coords.min(axis=0), coords.max(axis=0))).tolist()
        found = [d for d in description["cells"] if d["bounds_nm"] == bounds]
        if len(found) != 1:
            raise ValueError("native literal cell/target bounds bijection")
        desc = found[0]
        side = desc["side"]
        i, j, _ = desc["indices"]
        active = layout.polynomial.active[side]
        T = np.zeros((element.dim, len(active)), np.float64)
        T[active, np.arange(len(active))] = 1
        element.T_apply(T.ravel(), len(active), int(literal["permutations"][cell]))
        if np.any(T[np.setdiff1d(np.arange(element.dim), active)] != 0):
            raise ValueError(
                "native orientation moved boundary moments outside entity trace"
            )
        # The full transform is evaluated once; only bounded edge/face blocks
        # are retained or acted on, with largest block p6 face interior=60.
        groups = [
            ids
            for dim in (1, 2)
            for ids in element.entity_dofs[dim]
            if ids and ids[0] in active
        ]
        lookup = {int(v): k for k, v in enumerate(active)}
        local = T[active].T @ G[np.asarray(dofs)[active]].toarray()
        global_rows = layout.maps[side][i, j]
        phase = layout.weights[side][i, j]
        for group in groups:
            maximum_block = max(maximum_block, len(group))
            positions = [lookup[v] for v in group]
            owned = []
            for a in positions:
                row = int(global_rows[a])
                candidate = local[a] / phase[a]
                if row in coefficients:
                    old = coefficients[row]
                    den = max(np.linalg.norm(old), np.linalg.norm(candidate))
                    defect = np.linalg.norm(old - candidate) / den if den else 0.0
                    if defect > 1e-10:
                        raise ValueError(
                            "shared/periodic entity independent ownership inconsistency"
                        )
                    duplicates.append(float(defect))
                else:
                    coefficients[row] = candidate
                    owned.append(row)
            if owned:
                if len(owned) != len(group):
                    raise ValueError("complete high-order entity ownership split")
                ownership.append(
                    {
                        "cell": cell,
                        "reference_entity_dofs": list(map(int, group)),
                        "compact_rows": owned,
                    }
                )
    compact = np.array(sorted(coefficients), np.int64)
    rr = []
    cc = []
    vv = []
    for index, row in enumerate(compact):
        values = coefficients[int(row)]
        nz = np.flatnonzero(values != 0)
        rr.extend([index] * len(nz))
        cc.extend(nz)
        vv.extend(values[nz])
    E = coo_matrix(
        (np.array(vv, np.complex128), (rr, cc)), shape=(len(compact), n)
    ).tocsr()
    adapter = NativeBoundaryAdapter(
        E, compact, n, layout.rows, slaves, identity=description["name"]
    )
    return adapter, {
        "construction": "literal cell permutation + complete entity owner + primal MPC; no fit/QR/inverse",
        "largest_entity_transform": maximum_block,
        "small_linear_solves": 0,
        "ownership": ownership,
        "duplicate_max_relative": max(duplicates, default=0.0),
        "duplicate_row_checks": len(duplicates),
        "MPI": 1,
    }


class CoupledNativeBoundaryAction:
    """V + E^H B D E, with implicit original Hp=I at any port count."""

    def __init__(self, adapter, boundary, volume_apply):
        self.adapter, self.boundary, self.volume_apply = adapter, boundary, volume_apply
        if adapter.boundary_size != boundary.layout.rows:
            raise ValueError("native/boundary layout identity size")
        self.port_count = len(boundary.modes)
        self.original_hp_kind = "IMPLICIT_IDENTITY_NO_DENSE_PORT_MATRIX"

    def extract(self, value):
        return self.adapter.extract(value)

    def scatter(self, value):
        return self.adapter.scatter(value)

    def port_extract(self, value):
        return self.boundary.recover(self.extract(value))

    def modal_rhs(self, alpha):
        return self.scatter(self.boundary.modal_rhs(alpha))

    def apply(self, value, *, adjoint=False):
        x = self.adapter.independent(value)
        v = vector(
            self.volume_apply(x, adjoint=adjoint),
            self.adapter.native_size,
            "volume callback output",
        )
        return v + self.scatter(self.boundary.apply(self.extract(x), adjoint=adjoint))

    def augmented(self, value, alpha):
        x = self.adapter.independent(value)
        a = vector(alpha, self.port_count, "original port")
        return self.volume_apply(x, adjoint=False) + self.modal_rhs(
            a
        ), a - self.port_extract(x)

    def hp_apply(self, alpha):
        return vector(alpha, self.port_count, "implicit unit Hp").copy()


class LocalNativeVolumeAction:
    """Literal owner-cell multiply and MPC conjugate pullback, no global matrix.

    Tensors are borrowed from the existing native condensation class cache;
    the separately assembled FE matrix is exclusively an audit oracle.
    """

    def __init__(self, literal, tensors, class_indices, n):
        self.G = literal_expansion(literal, n)
        self.GH = self.G.conjugate().transpose().tocsr()
        self.dofs = literal["cell_dofs"]
        self.tensors = tensors
        self.class_indices = class_indices
        self.n = n
        self.calls = {"forward": 0, "adjoint": 0}
        self.seconds = {"forward": 0.0, "adjoint": 0.0}

    def __call__(self, value, *, adjoint=False):
        began = perf_counter()
        x = self.G @ vector(value, self.n, "native volume input")
        out = np.zeros(self.n, np.complex128)
        for dofs, index in zip(self.dofs, self.class_indices, strict=True):
            tensor = self.tensors[index]
            local = tensor.conjugate().T @ x[dofs] if adjoint else tensor @ x[dofs]
            np.add.at(out, dofs, local)
        out = self.GH @ out
        key = "adjoint" if adjoint else "forward"
        self.calls[key] += 1
        self.seconds[key] += perf_counter() - began
        return out
