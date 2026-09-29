"""Single-degree, matrix-free Maxwell trace/port action across FE/ML ABIs.

The packet contains original local volume tensors, exact cell elimination,
the original DtN carrier, and sparse Floquet pullbacks. It contains no global
FE matrix, global inverse, learned inverse, or accurate solution. Original
local tensors provide an independent uncondensed audit, never an audit CSR.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from time import perf_counter

import numpy as np


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def array_hash(value):
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def operation_relative(error, scale):
    return float(error / scale) if scale > 1e-12 else float(error)


class ActionPacket:
    """Exact S/S^H and original equations, only NumPy in the ML process."""

    def __init__(self, arrays):
        self.a = arrays
        self.nt = len(arrays["masters"])
        self.np = len(arrays["Hp"])
        self.size = self.nt + self.np
        self.nc, self.lt = arrays["tdofs"].shape
        self.li = arrays["idofs"].shape[1]
        self.full_rows = int(arrays["full_rows"])
        self.counts = {"S": 0, "SH": 0, "audit": 0}
        self.costs = {key: 0.0 for key in self.counts}
        self.bnorm = float(np.linalg.norm(arrays["b"]))
        if not self.bnorm > 0 or not np.isfinite(self.bnorm):
            raise ValueError("the physical scattered RHS must be finite and nonzero")
        for value in arrays.values():
            if not np.isfinite(value).all():
                raise ValueError("nonfinite action packet")
            value.setflags(write=False)

    def _expand(self, trace):
        a = self.a
        values = np.zeros(self.nc * self.lt, dtype=np.complex128)
        np.add.at(values, a["erows"], a["evals"] * trace[a["eids"]])
        return values.reshape(self.nc, self.lt)

    def _pullback(self, values):
        a = self.a
        result = np.zeros(self.nt, dtype=np.complex128)
        np.add.at(result, a["eids"], a["evals"].conj() * values.ravel()[a["erows"]])
        return result

    def _direct_B(self, alpha):
        a = self.a
        result = np.zeros(self.nt, dtype=np.complex128)
        np.add.at(result, a["br"], a["bv"] * alpha[a["bp"]])
        return result

    def _direct_D(self, trace):
        a = self.a
        result = np.zeros(self.np, dtype=np.complex128)
        np.add.at(result, a["dp"], a["dv"] * trace[a["dr"]])
        return result

    def apply(self, value, *, adjoint=False):
        began = perf_counter()
        name = "SH" if adjoint else "S"
        a = self.a
        value = np.asarray(value, dtype=np.complex128)
        if value.shape != (self.size,):
            raise ValueError("trace/port input inventory mismatch")
        trace, port = value[: self.nt], value[self.nt :]
        t = self._expand(trace)
        matrices = a["S"][a["classes"]]
        if adjoint:
            local = np.einsum("cij,ci->cj", matrices.conj(), t)
            local -= np.einsum("cpi,p->ci", a["Dhat"].conj(), port)
            output_port = np.einsum("cip,ci->p", a["Bhat"].conj(), t)
            output_port += a["Hhat"].conj().T @ port
            output_trace = self._pullback(local)
            np.add.at(output_trace, a["dr"], -a["dv"].conj() * port[a["dp"]])
            np.add.at(output_port, a["bp"], a["bv"].conj() * trace[a["br"]])
        else:
            local = np.einsum("cij,cj->ci", matrices, t)
            local += np.einsum("cip,p->ci", a["Bhat"], port)
            output_trace = self._pullback(local) + self._direct_B(port)
            output_port = -np.einsum("cpi,ci->p", a["Dhat"], t)
            output_port += a["Hhat"] @ port - self._direct_D(trace)
        result = np.r_[output_trace, output_port]
        self.counts[name] += 1
        self.costs[name] += perf_counter() - began
        return result

    def recover(self, value, *, rhs_i=None):
        a = self.a
        t = self._expand(value[: self.nt])
        i = np.einsum("cij,cj->ci", a["R"][a["classes"]], t)
        i += a["i_rhs"] if rhs_i is None else rhs_i
        i -= np.einsum("cip,p->ci", a["XiB"], value[self.nt :])
        field = np.zeros(self.full_rows, dtype=np.complex128)
        field[a["masters"]] = value[: self.nt]
        field[a["idofs"]] = i
        return field

    def uncondensed(self, field, alpha):
        """Original V field+B alpha, and D field-Hp alpha; no Schur audit."""
        a = self.a
        t = self._expand(field[a["masters"]])
        i = field[a["idofs"]]
        local = np.zeros((self.nc, self.lt + self.li), dtype=np.complex128)
        local[:, a["tpositions"]] = t
        local[:, a["ipositions"]] = i
        vf = np.einsum("cij,cj->ci", a["F"][a["classes"]], local)
        trace = self._pullback(vf[:, a["tpositions"]])
        trace += self._pullback(np.einsum("cip,p->ci", a["Bt"], alpha))
        trace += self._direct_B(alpha)
        internal = vf[:, a["ipositions"]] + np.einsum("cip,p->ci", a["Bi"], alpha)
        result = np.zeros(self.full_rows, dtype=np.complex128)
        result[a["masters"]] = trace
        result[a["idofs"]] = internal
        Df = np.einsum("cpi,ci->p", a["Dt"], t)
        Df += np.einsum("cpi,ci->p", a["Di"], i) + self._direct_D(field[a["masters"]])
        return result, Df - a["Hp"] @ alpha, Df

    def audit(self, value):
        """Independent original/native/port audit of a scattered iterate."""
        began = perf_counter()
        a = self.a
        field = self.recover(value)
        alpha = value[self.nt :]
        original, port, Df = self.uncondensed(field, alpha)
        rfe = a["g"] - original
        rp = a["gp"] + port
        augmented_rhs_norm = float(np.linalg.norm(np.r_[a["g"], a["gp"]]))
        augmented_norm = float(np.linalg.norm(np.r_[rfe, rp]))
        hp_rp = np.linalg.solve(a["Hp"], rp)
        correction = self._direct_B(hp_rp)
        correction += self._pullback(np.einsum("cip,p->ci", a["Bt"], hp_rp))
        native = rfe.copy()
        native[a["masters"]] -= correction
        native[a["idofs"]] -= np.einsum("cip,p->ci", a["Bi"], hp_rp)
        native_effective_rhs = a["g"].copy()
        hp_gp = np.linalg.solve(a["Hp"], a["gp"])
        native_effective_rhs[a["masters"]] -= self._direct_B(hp_gp)
        native_effective_rhs[a["masters"]] -= self._pullback(
            np.einsum("cip,p->ci", a["Bt"], hp_gp)
        )
        native_effective_rhs[a["idofs"]] -= np.einsum("cip,p->ci", a["Bi"], hp_gp)
        schur_r = a["b"] - self.apply(value)
        injected = np.zeros_like(a["g"])
        injected[a["masters"]] = schur_r[: self.nt]
        schur_identity = float(np.linalg.norm(rfe - injected))
        port_norm = float(np.linalg.norm(rp))
        port_scale = (
            float(np.linalg.norm(a["gp"]))
            + float(np.linalg.norm(Df))
            + float(np.linalg.norm(a["Hp"] @ alpha))
        )
        total_field = a["background"] + field
        total_alpha = a["background_alpha"] + alpha
        total_action, total_port, _ = self.uncondensed(total_field, total_alpha)
        total_r = a["total_g"] - total_action
        total_norm = float(np.linalg.norm(a["total_g"]))
        result = dict(
            schur_relative=float(np.linalg.norm(schur_r) / self.bnorm),
            augmented_relative=augmented_norm / augmented_rhs_norm,
            native_relative=float(
                np.linalg.norm(native) / np.linalg.norm(native_effective_rhs)
            ),
            original_total_augmented_relative=float(
                np.linalg.norm(np.r_[total_r, total_port]) / total_norm
            ),
            port_absolute=port_norm,
            port_full_rhs_relative=port_norm / augmented_rhs_norm,
            port_operation_relative=operation_relative(port_norm, port_scale),
            recovery_relative=float(
                np.linalg.norm(rfe[a["idofs"]]) / augmented_rhs_norm
            ),
            schur_original_identity_operation_relative=operation_relative(
                schur_identity,
                max(float(np.linalg.norm(original)), float(np.linalg.norm(a["g"]))),
            ),
            slave_storage_max=float(np.max(np.abs(field[a["slaves"]]), initial=0)),
            field_norm=float(np.linalg.norm(field)),
            port_unknown_norm=float(np.linalg.norm(alpha)),
        )
        result["strict_pass"] = (
            all(
                result[key] <= 1e-6
                for key in (
                    "schur_relative",
                    "augmented_relative",
                    "native_relative",
                    "original_total_augmented_relative",
                    "port_full_rhs_relative",
                    "port_operation_relative",
                    "recovery_relative",
                )
            )
            and result["slave_storage_max"] == 0.0
        )
        self.counts["audit"] += 1
        self.costs["audit"] += perf_counter() - began
        return result


def export_action_packet(
    action, space, g, gp, *, background, background_alpha, total_g
):
    """Export one p3 operator; only FE calls SciPy/local cell LU solves."""
    from scipy.linalg import lu_solve

    cells = action._cells
    c = action.condensed
    keys = list(c.retained_local_schur_by_class)
    lookup = {key: index for index, key in enumerate(keys)}
    nc, nt, ni, np_ = (
        len(cells),
        len(cells[0].original_trace),
        len(cells[0].original_interiors),
        c.appended_rows,
    )
    arrays = dict(
        S=np.stack([c.retained_local_schur_by_class[key] for key in keys]),
        F=np.stack([c.retained_local_original_by_class[key] for key in keys]),
        R=np.stack([c.interior_from_trace_by_class[key] for key in keys]),
        classes=np.array([lookup[cell.class_key] for cell in cells]),
        tdofs=np.stack([cell.original_trace for cell in cells]),
        idofs=np.stack([cell.original_interiors for cell in cells]),
        masters=np.asarray(c.trace_constraints.owned_active_original_dofs),
        slaves=np.setdiff1d(
            c.owned_trace_original_dofs, c.trace_constraints.owned_active_original_dofs
        ),
        full_rows=np.array(c.full_rows),
        Hp=action.H_p,
        Hhat=action.Hhat,
        g=np.array(g),
        gp=np.array(gp),
        b=action.reduce_rhs(g, port_rhs=gp, rhs_is_mpc_dual=True),
        i_rhs=np.stack(
            [lu_solve(cell.interior_lu, g[cell.original_interiors]) for cell in cells]
        ),
        background=np.array(background),
        background_alpha=np.array(background_alpha),
        total_g=np.array(total_g),
    )
    arrays["ipositions"] = np.asarray(
        space.element.basix_element.entity_dofs[3][0], dtype=np.int64
    )
    arrays["tpositions"] = np.setdiff1d(
        np.arange(space.element.space_dimension), arrays["ipositions"]
    )
    erows, eids, evals = [], [], []
    for index, cell in enumerate(cells):
        expansion = cell.expansion.tocoo()
        erows.extend(index * nt + expansion.row)
        eids.extend(cell.active_ids[expansion.col])
        evals.extend(expansion.data)
    for key, values in (("erows", erows), ("eids", eids), ("evals", evals)):
        arrays[key] = np.asarray(
            values, dtype=np.complex128 if key == "evals" else np.int64
        )
    for name, rows, cols in (
        ("Bi", ni, np_),
        ("Bt", nt, np_),
        ("XiB", ni, np_),
        ("Bhat", nt, np_),
        ("Di", np_, ni),
        ("Dt", np_, nt),
        ("Dhat", np_, nt),
    ):
        values = np.zeros((nc, rows, cols), dtype=np.complex128)
        for index, cell in enumerate(cells):
            if name in ("Di", "Dt", "Dhat"):
                values[index, cell.ports, :] = getattr(cell, name)
            else:
                values[index][:, cell.ports] = getattr(cell, name)
        arrays[name] = values
    for prefix, data in (
        ("b", action._direct_B_active),
        ("d", action._direct_D_active),
    ):
        rows, ports, values = [], [], []
        for port, (ids, coefficients) in data.items():
            rows.extend(ids)
            ports.extend([port] * len(ids))
            values.extend(coefficients)
        arrays[prefix + "r"] = np.asarray(rows, dtype=np.int64)
        arrays[prefix + "p"] = np.asarray(ports, dtype=np.int64)
        arrays[prefix + "v"] = np.asarray(values, dtype=np.complex128)
    return ActionPacket(arrays)


def capacity_before_allocation(inventory, port_count):
    """Worst-case unique-class/copy bound, not a measured RSS claim."""
    nc, dim = inventory["cells"], inventory["cell_dimension"]
    lt, li = 12 * 3 + 6 * 2 * 3 * 2, 3 * 3 * 2**2
    if inventory["degree"] != 3 or dim != lt + li:
        raise ValueError("this frozen pilot is p3 only")
    local = nc * (dim**2 + lt**2 + 2 * li * lt + li**2) * 16
    port = nc * (4 * lt + 3 * li) * port_count * 16
    packet_and_transient = 4 * (local + port) + 256 * 2**20
    libraries_jit = 3 * 2**30
    optimizer_activations = 1 * 2**30
    total = packet_and_transient + libraries_jit + optimizer_activations
    if (
        inventory["full_fe_rows"] > 200000
        or inventory["independent_trace_rows"] > 100000
        or total >= 12 * 2**30
    ):
        raise MemoryError("preallocation inventory violates reviewed pilot limit")
    return dict(
        status="PREALLOCATION_PASS",
        scope="p3 single-degree candidate and independent native cell audit",
        full_rows=inventory["full_fe_rows"],
        independent_trace_rows=inventory["independent_trace_rows"],
        ports=port_count,
        maximum_unique_classes=nc,
        local_arrays_upper_bytes=local,
        port_arrays_upper_bytes=port,
        packet_copies_and_transient_upper_bytes=packet_and_transient,
        libraries_compiler_upper_bytes=libraries_jit,
        optimizer_activations_upper_bytes=optimizer_activations,
        total_upper_bytes=total,
        warning_bytes=12 * 2**30,
        hard_bytes=16 * 2**30,
        global_FE_matrix=False,
        global_p4_factor=False,
        private_audit_CSR=False,
    )
