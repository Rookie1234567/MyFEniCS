from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np

from .local_slab_solver import LocalCsrOperator, LocalSlabSolver, ScipyCsrAction
import time


SCHEMA = "myfenics.batched_linear_reduced_smoother.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class FrozenLinearReducedMap:
    input_basis: np.ndarray
    reduced_map: np.ndarray
    output_basis: np.ndarray
    operator_fingerprint: str
    checkpoint_sha256: str = "unwritten"

    def __post_init__(self) -> None:
        input_basis = np.asarray(self.input_basis, dtype=np.complex128)
        reduced_map = np.asarray(self.reduced_map, dtype=np.complex128)
        output_basis = np.asarray(self.output_basis, dtype=np.complex128)
        if input_basis.ndim != 2 or output_basis.ndim != 2 or reduced_map.ndim != 2:
            raise ValueError("linear reduced checkpoint arrays must be matrices")
        if reduced_map.shape != (output_basis.shape[1], input_basis.shape[1]):
            raise ValueError("linear reduced checkpoint ranks do not match")
        if input_basis.shape[0] != output_basis.shape[0]:
            raise ValueError("linear reduced input/output sizes do not match")
        if not all(np.all(np.isfinite(a)) for a in (input_basis, reduced_map, output_basis)):
            raise ValueError("linear reduced checkpoint contains NaN or Inf")
        object.__setattr__(self, "input_basis", np.ascontiguousarray(input_basis))
        object.__setattr__(self, "reduced_map", np.ascontiguousarray(reduced_map))
        object.__setattr__(self, "output_basis", np.ascontiguousarray(output_basis))

    @property
    def size(self) -> int:
        return int(self.input_basis.shape[0])

    @property
    def storage_bytes(self) -> int:
        return int(self.input_basis.nbytes + self.reduced_map.nbytes + self.output_basis.nbytes)

    def predict(self, rhs: np.ndarray) -> np.ndarray:
        source = np.asarray(rhs, dtype=np.complex128)
        if source.shape != (self.size,):
            raise ValueError("linear reduced input has the wrong shape")
        return self.output_basis @ (self.reduced_map @ (self.input_basis.conj().T @ source))

    def predict_many(self, rhs: np.ndarray) -> np.ndarray:
        source = np.asarray(rhs, dtype=np.complex128)
        if source.ndim != 2 or source.shape[1] != self.size:
            raise ValueError("linear reduced batch has the wrong shape")
        coordinates = source @ self.input_basis.conj()
        return (coordinates @ self.reduced_map.T) @ self.output_basis.T

    def save(self, directory: Path, **metadata: object) -> None:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        weights = target / "weights.npz"
        np.savez_compressed(weights, input_basis=self.input_basis, reduced_map=self.reduced_map, output_basis=self.output_basis)
        manifest = {"schema": SCHEMA, "operator_fingerprint": self.operator_fingerprint, "weights_sha256": _sha256(weights), **metadata}
        (target / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, directory: Path, *, expected_operator_fingerprint: str | None = None) -> "FrozenLinearReducedMap":
        source = Path(directory)
        manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        weights = source / "weights.npz"
        checksum = _sha256(weights)
        if manifest.get("schema") != SCHEMA or checksum != manifest.get("weights_sha256"):
            raise ValueError("invalid linear reduced checkpoint")
        fingerprint = str(manifest.get("operator_fingerprint", ""))
        if expected_operator_fingerprint is not None and fingerprint != expected_operator_fingerprint:
            raise ValueError("linear reduced operator fingerprint mismatch")
        with np.load(weights, allow_pickle=False) as payload:
            return cls(payload["input_basis"], payload["reduced_map"], payload["output_basis"], fingerprint, checksum)


class FusedLinearReducedAction:
    def __init__(self, operator: LocalCsrOperator, model: FrozenLinearReducedMap) -> None:
        if model.operator_fingerprint != operator.fingerprint:
            raise ValueError("model/operator fingerprint mismatch")
        self.model = model
        self.action = ScipyCsrAction(operator)

    def predict_and_audit_many(self, rhs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        candidate = self.model.predict_many(rhs)
        residual = np.asarray(rhs, dtype=np.complex128) - self.action.action_many(candidate)
        return candidate, np.linalg.norm(residual, axis=1) / np.maximum(np.linalg.norm(rhs, axis=1), np.finfo(float).tiny)


class IluLinearReducedCorrectionSlabSolver:
    """One ILU action plus a frozen linear correction, with exact fused audits."""

    def __init__(self, operator: LocalCsrOperator, model: FrozenLinearReducedMap, ilu_solver: LocalSlabSolver, *, shadow: bool, nondegradation_tolerance: float = 1e-12) -> None:
        if model.operator_fingerprint != operator.fingerprint:
            raise ValueError("model/operator fingerprint mismatch")
        self.model = model
        self.ilu_solver = ilu_solver
        self.action = ScipyCsrAction(operator)
        self.shadow = bool(shadow)
        self.nondegradation_tolerance = float(nondegradation_tolerance)
        self.apply_count = 0
        self.accept_count = 0
        self.elapsed_s = 0.0
        self.baseline_rhos: list[float] = []
        self.candidate_rhos: list[float] = []

    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None:
        started = time.perf_counter()
        source = np.asarray(rhs, dtype=np.complex128)
        baseline = np.empty_like(source)
        self.ilu_solver.solve(source, baseline)
        q = source - self.action.action(baseline)
        delta = self.model.predict(q)
        candidate_residual = q - self.action.action(delta)
        denominator = max(float(np.linalg.norm(source)), np.finfo(float).tiny)
        baseline_rho = float(np.linalg.norm(q) / denominator)
        candidate_rho = float(np.linalg.norm(candidate_residual) / denominator)
        accepted = bool(np.all(np.isfinite(delta)) and candidate_rho <= baseline_rho * (1.0 + self.nondegradation_tolerance))
        out[:] = baseline if self.shadow or not accepted else baseline + delta
        self.apply_count += 1
        self.accept_count += int(accepted)
        self.baseline_rhos.append(baseline_rho)
        self.candidate_rhos.append(candidate_rho)
        self.elapsed_s += time.perf_counter() - started

    @property
    def diagnostics(self) -> dict[str, object]:
        baseline = np.asarray(self.baseline_rhos)
        candidate = np.asarray(self.candidate_rhos)
        return {
            "identity": "ilu_linear_reduced_shadow" if self.shadow else "ilu_linear_reduced_active",
            "apply_count": self.apply_count,
            "accept_count": self.accept_count,
            "accept_fraction": self.accept_count / max(self.apply_count, 1),
            "elapsed_s": self.elapsed_s,
            "mean_elapsed_s": self.elapsed_s / max(self.apply_count, 1),
            "baseline_rho_median": float(np.median(baseline)) if baseline.size else None,
            "candidate_rho_median": float(np.median(candidate)) if candidate.size else None,
            "candidate_rho_p95": float(np.quantile(candidate, .95)) if candidate.size else None,
            "model_storage_bytes": self.model.storage_bytes,
            "checkpoint_sha256": self.model.checkpoint_sha256,
            "ilu": self.ilu_solver.diagnostics,
        }

    def destroy(self) -> None:
        self.ilu_solver.destroy()
