"""Opt-in weak-form pure source transfer, separate from Schwarz sweeps.

The caller supplies adjacent-two-layer PML solves, orientation-aware maps,
and the original global L2 mass inverse. All exchanged sources are dual FE
vectors. No edge coefficient is multiplied by a cutoff in this module.
The discretization, PML parameters and endpoint boundary conditions belong
to the caller and must be recorded in its experiment configuration.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np


def smooth_cutoff(z: Any, left: float, right: float, *, increasing: bool = False) -> Any:
    """C1 cubic cutoff, constant outside the given physical interval.

    For numeric arrays this returns a NumPy array (or scalar). For a UFL
    expression the returned expression is differentiated by UFL, not sampled
    at edge locations. ``increasing=False`` means one on the left, zero right.
    """
    if not np.isfinite(left) or not np.isfinite(right) or right <= left:
        raise ValueError("cutoff interval must be finite and increasing")
    if isinstance(z, (int, float, np.number, np.ndarray, list, tuple)):
        t = np.clip((np.asarray(z) - left) / (right - left), 0.0, 1.0)
        value = t * t * (3.0 - 2.0 * t)
        return value if increasing else 1.0 - value
    import ufl

    t = (z - left) / (right - left)
    value = ufl.conditional(ufl.le(z, left), 0.0,
                            ufl.conditional(ufl.ge(z, right), 1.0,
                                            t * t * (3.0 - 2.0 * t)))
    return value if increasing else 1.0 - value


def weak_cutoff_commutator(u: Any, v: Any, beta: Any, mu_inverse: Any = 1.0) -> Any:
    """UFL density for a(beta*u,v)-a(u,beta*v), real scalar beta.

    ``a`` uses curl(mu^-1 curl)-k0^2 epsilon and conjugates its test
    argument. Multiplication by a scalar or a 3x3 UFL permeability inverse is
    supported. Mass terms cancel. Integrate this density on the transition
    layer with the caller's measure; no PML/physical material cache is used.
    """
    import ufl

    grad_beta = ufl.grad(beta)
    return (ufl.inner(mu_inverse * ufl.cross(grad_beta, u), ufl.curl(v))
            - ufl.inner(mu_inverse * ufl.curl(u), ufl.cross(grad_beta, v)))


def curl_product(beta: Any, curl_e: Any, grad_beta: Any, e: Any) -> np.ndarray:
    """Pointwise NumPy oracle for curl(beta E), not a DOF transfer."""
    return np.asarray(beta)[..., None] * np.asarray(curl_e) + np.cross(grad_beta, e)


@dataclass(frozen=True)
class TransferResult:
    field: np.ndarray
    statistics: dict[str, Any]


class PureSourceTransfer:
    """Two independent cumulative source passes with conforming projection.

    All matrices map the global independent FE *primal* vector to a global
    FE *dual* vector. ``partition_mass[i]`` integrates over physical layer i;
    ``forward_beta_mass[i]`` integrates beta_i^+ on that same layer.
    Their dimensions must be identical. The mass inverse is an L2 Riesz
    lifting, never an interpretation of a condensed trace as a volume source.

    ``solve_pair(i, load)`` maps a global dual load to an opaque local primal
    vector on layers i,i+1 plus PML. It must impose the caller's local endpoint
    conditions and perform consistent dual restriction and primal lifting.
    ``forward_commutator(i,u)`` returns the global dual vector C_beta u for
    decreasing beta on layer i+1. ``reverse_commutator(i,u)`` uses increasing
    beta on layer i. These are weak commutators, not A times a nodally masked
    field, and must have transition-layer support.

    ``reconstruct_load(layer,up,down)`` returns the global weak mass load of
    up+down on that layer. A missing endpoint field is None. The final mass
    solve projects the piecewise reconstructed fields into the conforming
    Floquet space. Only the forward fields and one reverse field are retained.
    The global Maxwell operator is deliberately absent: this is not the
    multiplicative Schwarz update r <- r-A*delta.
    """

    def __init__(
        self,
        *,
        partition_mass: Sequence[Any],
        forward_beta_mass: Sequence[Any],
        mass_solve: Callable[[np.ndarray], np.ndarray],
        solve_pair: Callable[[int, np.ndarray], np.ndarray],
        forward_commutator: Callable[[int, np.ndarray], np.ndarray],
        reverse_commutator: Callable[[int, np.ndarray], np.ndarray],
        reconstruct_load: Callable[[int, np.ndarray | None, np.ndarray | None], np.ndarray],
        lifting_tolerance: float = 1.0e-10,
    ) -> None:
        self.partition_mass = tuple(partition_mass)
        self.forward_beta_mass = tuple(forward_beta_mass)
        self.layer_count = len(self.partition_mass)
        if self.layer_count < 2 or len(self.forward_beta_mass) != self.layer_count:
            raise ValueError("at least two physical layers and one beta mass per layer required")
        shape = self.partition_mass[0].shape
        if len(shape) != 2 or shape[0] != shape[1] or shape[0] == 0:
            raise ValueError("mass operators must be nonempty square matrices")
        if any(m.shape != shape for m in self.partition_mass + self.forward_beta_mass):
            raise ValueError("mass operators must share the independent global FE layout")
        if not np.isfinite(lifting_tolerance) or lifting_tolerance <= 0.0:
            raise ValueError("lifting tolerance must be finite and positive")
        self.size = shape[0]
        self.mass_solve = mass_solve
        self.solve_pair = solve_pair
        self.forward_commutator = forward_commutator
        self.reverse_commutator = reverse_commutator
        self.reconstruct_load = reconstruct_load
        self.lifting_tolerance = float(lifting_tolerance)
        self.apply_count = 0
        self.last_statistics: dict[str, Any] | None = None

    def _dual(self, value: Any, label: str) -> np.ndarray:
        result = np.asarray(value, dtype=np.complex128)
        if result.shape != (self.size,) or not np.isfinite(result).all():
            raise ValueError(f"{label} must be a finite global FE vector")
        return result

    @staticmethod
    def _local(value: Any) -> np.ndarray:
        result = np.asarray(value, dtype=np.complex128).copy()
        if result.ndim != 1 or result.size == 0 or not np.isfinite(result).all():
            raise ValueError("local solve returned a nonfinite or invalid primal vector")
        return result

    def apply(self, residual: np.ndarray) -> TransferResult:
        """Apply the frozen linear source-transfer construction to a fresh dual RHS."""
        start = perf_counter()
        rhs = self._dual(residual, "residual").copy()
        source = self._dual(self.mass_solve(rhs), "Riesz lift")
        originals = [self._dual(m @ source, "layer source") for m in self.partition_mass]
        denom = max(float(np.linalg.norm(rhs)), np.finfo(float).tiny)
        lift_error = float(np.linalg.norm(sum(originals, np.zeros_like(rhs)) - rhs) / denom)
        if lift_error > self.lifting_tolerance:
            raise ValueError(f"partitioned L2 lifting residual {lift_error} exceeds tolerance")
        lift_seconds = perf_counter() - start
        forward: list[np.ndarray | None] = []
        solve_seconds = 0.0
        transfer_seconds = 0.0
        bar = originals[0].copy()
        for pair in range(self.layer_count - 1):
            tick = perf_counter()
            u = self._local(self.solve_pair(pair, bar + originals[pair + 1]))
            solve_seconds += perf_counter() - tick
            forward.append(u)
            if pair < self.layer_count - 2:
                tick = perf_counter()
                weighted_source = self._dual(self.forward_beta_mass[pair + 1] @ source,
                                              "weighted original source")
                transferred = self._dual(self.forward_commutator(pair, u), "forward commutator")
                bar = originals[pair + 1] - weighted_source - transferred
                transfer_seconds += perf_counter() - tick
        reconstruction_seconds = 0.0
        tick = perf_counter()
        reconstructed = self._dual(self.reconstruct_load(self.layer_count - 1, forward[-1], None),
                                    "top-layer reconstruction").copy()
        forward[-1] = None
        reconstruction_seconds += perf_counter() - tick
        bar = originals[-1].copy()
        for pair in range(self.layer_count - 2, -1, -1):
            tick = perf_counter()
            load = bar + originals[0] if pair == 0 else bar
            u = self._local(self.solve_pair(pair, load))
            solve_seconds += perf_counter() - tick
            tick = perf_counter()
            up = forward[pair - 1] if pair > 0 else None
            reconstructed += self._dual(self.reconstruct_load(pair, up, u), "layer reconstruction")
            if pair > 0:
                forward[pair - 1] = None
            reconstruction_seconds += perf_counter() - tick
            if pair > 0:
                tick = perf_counter()
                transferred = self._dual(self.reverse_commutator(pair, u), "reverse commutator")
                bar = originals[pair] - transferred
                transfer_seconds += perf_counter() - tick
        tick = perf_counter()
        field = self._dual(self.mass_solve(reconstructed), "conforming reconstruction").copy()
        projection_seconds = perf_counter() - tick
        self.apply_count += 1
        statistics = {
            "apply_index": self.apply_count,
            "layer_count": self.layer_count,
            "local_solve_count": 2 * (self.layer_count - 1),
            "forward_transfer_count": self.layer_count - 2,
            "reverse_transfer_count": self.layer_count - 2,
            "mass_solve_count": 2,
            "maximum_retained_forward_fields": self.layer_count - 1,
            "partition_lifting_relative_residual": lift_error,
            "original_layer_source_norms": [float(np.linalg.norm(value)) for value in originals],
            "lifting_seconds": lift_seconds,
            "local_solves_seconds": solve_seconds,
            "source_transfer_seconds": transfer_seconds,
            "reconstruction_load_seconds": reconstruction_seconds,
            "projection_seconds": projection_seconds,
            "wall_seconds": perf_counter() - start,
        }
        self.last_statistics = statistics.copy()
        return TransferResult(field, statistics)

    def __call__(self, residual: np.ndarray) -> np.ndarray:
        return self.apply(residual).field
