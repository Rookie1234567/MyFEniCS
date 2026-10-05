"""Exact input-support reuse of the original native Maxwell action.

Only the input of a new local wave has compact support. All cells touched by
that support after the original MPC expansion, all output rows of those cells,
and the complete DtN blocks are retained. No matrix inverse, trace Schur action,
threshold pruning or new physical operator is constructed. Accepted fields and
their residual audits continue to use FullNativePacket.apply/audit.
"""

from time import perf_counter

import numpy as np


class LocalWaveAction:
    """A[:, support] and its exact adjoint, not a replacement full FE operator."""

    def __init__(self, action, support):
        start = perf_counter()
        self.action = action
        self.support = np.unique(np.asarray(support, dtype=np.int64))
        if not len(self.support) or np.any(self.support < 0) or np.any(
            self.support >= action.size
        ):
            raise ValueError("LOCAL_WAVE_INPUT_SUPPORT_INVALID")
        self.mask = np.zeros(action.size, dtype=bool)
        self.mask[self.support] = True
        a = action.a
        entry_cells = a["erows"] // action.dim
        # Include periodic images and neighbour cells sharing an input master.
        self.cells = np.unique(entry_cells[self.mask[a["eids"]]])
        cell_map = np.full(action.nc, -1, dtype=np.int64)
        cell_map[self.cells] = np.arange(len(self.cells))
        selected = cell_map[entry_cells] >= 0
        self.eids = a["eids"][selected]
        self.erows = (
            cell_map[entry_cells[selected]] * action.dim
            + a["erows"][selected] % action.dim
        )
        self.evals = a["evals"][selected]
        self.classes = a["classes"][self.cells]
        self.input_entries = self.mask[self.eids]
        # Include every original nonzero DtN output entry, even tiny traces.
        self.output_rows = np.unique(np.r_[self.eids, a["br"]])
        self.counts = dict(columns=0, adjoint=0)
        self.seconds = dict(build=perf_counter() - start, columns=0.0, adjoint=0.0)

    def _tensors(self, local, *, adjoint):
        """At most eight original cell tensors are gathered at a time."""
        out = np.empty_like(local)
        for first in range(0, len(self.cells), 8):
            section = slice(first, first + 8)
            tensors = self.action.a["F"][self.classes[section]]
            out[section] = (
                np.einsum("cij,cik->cjk", tensors.conj(), local[section])
                if adjoint
                else np.einsum("cij,cjk->cik", tensors, local[section])
            )
        return out

    def columns(self, columns):
        """Return the complete original A times a bounded local column block."""
        start = perf_counter()
        action = self.action
        columns = np.asarray(columns)
        if (
            columns.ndim != 2
            or columns.shape[0] != action.size
            or columns.dtype != np.complex128
            or not 1 <= columns.shape[1] <= 24
            or not np.isfinite(columns).all()
            or np.any(columns[~self.mask] != 0)
        ):
            raise ValueError("LOCAL_WAVE_COLUMNS_OUTSIDE_PROVEN_SUPPORT_OR_LAYOUT")
        width = columns.shape[1]
        local = np.zeros((len(self.cells) * action.dim, width), complex)
        np.add.at(local, self.erows, self.evals[:, None] * columns[self.eids])
        values = self._tensors(local.reshape(-1, action.dim, width), adjoint=False)
        out = np.zeros_like(columns)
        np.add.at(
            out, self.eids,
            self.evals.conj()[:, None] * values.reshape(-1, width)[self.erows],
        )
        port_before = action.costs["port_solve"]
        for j in range(width):
            out[:, j] += action.B(action.port_solve(action.D(columns[:, j])))
        elapsed = perf_counter() - start
        action.counts["A"] += width
        action.costs["A"] += elapsed - (action.costs["port_solve"] - port_before)
        self.counts["columns"] += width
        self.seconds["columns"] += elapsed
        return out

    def adjoint(self, cotangent):
        """Return the needed coordinates of A* cotangent; others explicitly zero."""
        start = perf_counter()
        action = self.action
        cotangent = action._vector(cotangent)
        local = np.zeros(len(self.cells) * action.dim, complex)
        np.add.at(local, self.erows, self.evals * cotangent[self.eids])
        values = self._tensors(local.reshape(-1, action.dim, 1), adjoint=True)
        out = np.zeros(action.size, complex)
        entries = self.input_entries
        np.add.at(
            out, self.eids[entries],
            self.evals[entries].conj() * values.ravel()[self.erows[entries]],
        )
        port_before = action.costs["port_solve"]
        port = action.D(action.port_solve(action.B(cotangent, True)), True)
        out[self.support] += port[self.support]
        elapsed = perf_counter() - start
        action.counts["AH"] += 1
        action.costs["AH"] += elapsed - (action.costs["port_solve"] - port_before)
        self.counts["adjoint"] += 1
        self.seconds["adjoint"] += elapsed
        return out

    @property
    def retained_bytes(self):
        return sum(
            value.nbytes for value in vars(self).values() if isinstance(value, np.ndarray)
        )
