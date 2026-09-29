"""Full independent Nedelec coefficients, original volume and exact DtN.

No interior elimination, Maxwell inverse, global Maxwell CSR or target solution
is retained. The real-parameter derivative convention is Re(g^H dc).
"""

from time import perf_counter

import numpy as np

from src.solvers.neural_fe_action_packet import array_hash, operation_relative


class FullNativePacket:
    def __init__(self, arrays):
        self.a = arrays
        self.size = len(arrays["masters"])
        self.full_rows = int(arrays["full_rows"])
        self.nc, self.dim = arrays["cell_dofs"].shape
        self.np = len(arrays["H"])
        self.counts = dict(A=0, AH=0, audit=0, port_solve=0)
        self.costs = {k: 0.0 for k in self.counts}
        if arrays["F"].shape[1:] != (self.dim, self.dim):
            raise ValueError("local original tensor shape mismatch")
        if np.any(arrays["H"] <= 0) or not np.isrealobj(arrays["H"]):
            raise ValueError(
                "PORT_ELIMINATION_NOT_QUALIFIED: nonpositive original normalization"
            )
        for key, value in arrays.items():
            if not np.isfinite(value).all():
                raise ValueError(f"nonfinite {key}")
            value.setflags(write=False)
        self.f = arrays["g"] - self.B(self.port_solve(arrays["gp"]))
        self.bnorm = float(np.linalg.norm(self.f))
        if not self.bnorm > 0 or not np.isfinite(self.bnorm):
            raise ValueError("physical scattered load must be finite and nonzero")

    def _vector(self, c):
        c = np.asarray(c)
        if (
            c.shape != (self.size,)
            or c.dtype != np.complex128
            or not np.isfinite(c).all()
        ):
            raise ValueError("finite complex128 full independent FE vector required")
        return c

    def expand(self, c):
        c = self._vector(c)
        a = self.a
        local = np.zeros(self.nc * self.dim, dtype=np.complex128)
        np.add.at(local, a["erows"], a["evals"] * c[a["eids"]])
        return local.reshape(self.nc, self.dim)

    def pullback(self, local):
        a = self.a
        out = np.zeros(self.size, dtype=np.complex128)
        np.add.at(out, a["eids"], a["evals"].conj() * local.ravel()[a["erows"]])
        return out

    def volume(self, c, adjoint=False):
        a = self.a
        local = self.expand(c)
        tensors = a["F"][a["classes"]]
        values = (
            np.einsum("cij,ci->cj", tensors.conj(), local)
            if adjoint
            else np.einsum("cij,cj->ci", tensors, local)
        )
        return self.pullback(values)

    def B(self, alpha, adjoint=False):
        a = self.a
        if adjoint:
            result = np.zeros(self.np, dtype=np.complex128)
            np.add.at(result, a["bp"], a["bv"].conj() * alpha[a["br"]])
        else:
            result = np.zeros(self.size, dtype=np.complex128)
            np.add.at(result, a["br"], a["bv"] * alpha[a["bp"]])
        return result

    def D(self, c, adjoint=False):
        a = self.a
        if adjoint:
            result = np.zeros(self.size, dtype=np.complex128)
            np.add.at(result, a["dr"], a["dv"].conj() * c[a["dp"]])
        else:
            result = np.zeros(self.np, dtype=np.complex128)
            np.add.at(result, a["dp"], a["dv"] * c[a["dr"]])
        return result

    def port_solve(self, rhs):
        # Hp is the original diagonal surface normalization, not Hhat.
        start = perf_counter()
        result = np.asarray(rhs, dtype=np.complex128) / self.a["H"]
        self.counts["port_solve"] += 1
        self.costs["port_solve"] += perf_counter() - start
        return result

    def alpha(self, c):
        # Actual augmented blocks: [V B; -D H].
        return self.port_solve(self.a["gp"] + self.D(c))

    def apply(self, c, *, adjoint=False):
        start = perf_counter()
        c = self._vector(c)
        port_before = self.costs["port_solve"]
        if adjoint:
            value = self.volume(c, True) + self.D(
                self.port_solve(self.B(c, True)), True
            )
        else:
            value = self.volume(c) + self.B(self.port_solve(self.D(c)))
        name = "AH" if adjoint else "A"
        self.counts[name] += 1
        self.costs[name] += (
            perf_counter() - start - (self.costs["port_solve"] - port_before)
        )
        return value

    def storage(self, c):
        result = np.zeros(self.full_rows, dtype=np.complex128)
        result[self.a["masters"]] = self._vector(c)
        return result

    def audit(self, c):
        start = perf_counter()
        port_before = self.costs["port_solve"]
        a = self.a
        c = self._vector(c)
        alpha = self.alpha(c)
        vc, bc, dc = self.volume(c), self.B(alpha), self.D(c)
        rfe = a["g"] - vc - bc
        rp = a["gp"] + dc - a["H"] * alpha
        native = self.f - vc - self.B(self.port_solve(dc))
        rhs_aug = float(np.linalg.norm(np.r_[a["g"], a["gp"]]))
        scale_port = float(
            np.linalg.norm(a["gp"])
            + np.linalg.norm(dc)
            + np.linalg.norm(a["H"] * alpha)
        )
        total_c = a["background"] + c
        total_alpha = a["background_alpha"] + alpha
        rt = a["total_g"] - self.volume(total_c) - self.B(total_alpha)
        rpt = self.D(total_c) - a["H"] * total_alpha
        result = dict(
            native_relative=float(np.linalg.norm(native) / self.bnorm),
            augmented_relative=float(np.linalg.norm(np.r_[rfe, rp]) / rhs_aug),
            original_total_augmented_relative=float(
                np.linalg.norm(np.r_[rt, rpt]) / np.linalg.norm(a["total_g"])
            ),
            port_absolute=float(np.linalg.norm(rp)),
            port_full_rhs_relative=float(np.linalg.norm(rp) / rhs_aug),
            port_operation_relative=operation_relative(np.linalg.norm(rp), scale_port),
            augmented_rhs_norm=rhs_aug,
            native_rhs_norm=self.bnorm,
            slave_storage_max=float(
                np.max(np.abs(self.storage(c)[a["slaves"]]), initial=0)
            ),
            interior_coefficient_norm=float(
                np.linalg.norm(self.storage(c)[a["idofs"]])
            ),
            full_coefficient_norm=float(np.linalg.norm(c)),
            port_unknown_norm=float(np.linalg.norm(alpha)),
        )
        result["strict_pass"] = (
            all(
                result[k] <= 1e-6
                for k in (
                    "native_relative",
                    "augmented_relative",
                    "original_total_augmented_relative",
                    "port_full_rhs_relative",
                    "port_operation_relative",
                )
            )
            and result["slave_storage_max"] == 0
        )
        self.counts["audit"] += 1
        self.costs["audit"] += (
            perf_counter() - start - (self.costs["port_solve"] - port_before)
        )
        return result


class ResidualMetric:
    def __init__(self, action, gram=None):
        self.action, self.gram = action, gram
        self.denominator = (
            float(np.vdot(action.f, action.f).real)
            if gram is None
            else float(np.vdot(action.f, gram.solve(action.f)).real)
        )
        if self.denominator <= 0 or not np.isfinite(self.denominator):
            raise ValueError("nonzero fixed Riesz/Euclidean load scale required")

    def value(self, c, *, gradient=False):
        r = self.action.apply(c) - self.action.f
        q = r if self.gram is None else self.gram.solve(r)
        dot = np.vdot(r, q)
        if abs(dot.imag) > 1e-10 * max(abs(dot.real), 1e-30) or dot.real < -1e-20:
            raise ValueError("invalid residual metric")
        loss = float(dot.real / (2 * self.denominator))
        g = self.action.apply(q, adjoint=True) / self.denominator if gradient else None
        return loss, r, g


def load_native(path):
    with np.load(path, allow_pickle=False) as data:
        return FullNativePacket({k: np.array(data[k]) for k in data.files})


def packet_hashes(packet):
    return {key: array_hash(value) for key, value in packet.a.items()}
