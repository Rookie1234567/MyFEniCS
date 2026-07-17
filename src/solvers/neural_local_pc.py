from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

from .local_slab_solver import LocalCsrOperator, LocalSlabSolver, relative_local_residual


CHECKPOINT_SCHEMA = "myfenics.neural_local_pc.v1"
TINY = np.finfo(float).tiny


def pack_complex(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.complex128)
    return np.concatenate((array.real, array.imag)).astype(np.float64, copy=False)


def unpack_complex(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size % 2:
        raise ValueError("packed complex array must be one-dimensional and even-sized")
    half = array.size // 2
    return array[:half] + 1j * array[half:]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class FrozenNumpyMlp:
    input_basis: np.ndarray
    output_basis: np.ndarray
    weight_1: np.ndarray
    bias_1: np.ndarray
    weight_2: np.ndarray
    bias_2: np.ndarray
    operator_fingerprint: str
    checkpoint_sha256: str

    def __post_init__(self) -> None:
        input_basis = np.asarray(self.input_basis, dtype=np.float64)
        output_basis = np.asarray(self.output_basis, dtype=np.float64)
        weight_1 = np.asarray(self.weight_1, dtype=np.float64)
        bias_1 = np.asarray(self.bias_1, dtype=np.float64)
        weight_2 = np.asarray(self.weight_2, dtype=np.float64)
        bias_2 = np.asarray(self.bias_2, dtype=np.float64)
        if input_basis.ndim != 2 or output_basis.ndim != 2:
            raise ValueError("checkpoint POD bases must be matrices")
        if weight_1.shape[1] != input_basis.shape[1]:
            raise ValueError("checkpoint input-basis/hidden shape mismatch")
        if bias_1.shape != (weight_1.shape[0],):
            raise ValueError("checkpoint hidden bias shape mismatch")
        if weight_2.shape != (output_basis.shape[1], weight_1.shape[0]):
            raise ValueError("checkpoint hidden/output shape mismatch")
        if bias_2.shape != (output_basis.shape[1],):
            raise ValueError("checkpoint output bias shape mismatch")
        arrays = (input_basis, output_basis, weight_1, bias_1, weight_2, bias_2)
        if not all(np.all(np.isfinite(array)) for array in arrays):
            raise ValueError("checkpoint contains NaN or Inf")
        object.__setattr__(self, "input_basis", input_basis)
        object.__setattr__(self, "output_basis", output_basis)
        object.__setattr__(self, "weight_1", weight_1)
        object.__setattr__(self, "bias_1", bias_1)
        object.__setattr__(self, "weight_2", weight_2)
        object.__setattr__(self, "bias_2", bias_2)

    @property
    def packed_size(self) -> int:
        return int(self.input_basis.shape[0])

    @property
    def storage_bytes(self) -> int:
        return int(
            sum(
                array.nbytes
                for array in (
                    self.input_basis,
                    self.output_basis,
                    self.weight_1,
                    self.bias_1,
                    self.weight_2,
                    self.bias_2,
                )
            )
        )

    def predict(self, rhs: np.ndarray) -> np.ndarray:
        packed = pack_complex(rhs)
        if packed.shape != (self.packed_size,):
            raise ValueError("checkpoint and local residual sizes differ")
        scale = max(float(np.linalg.norm(packed)), TINY)
        coordinates = self.input_basis.T @ (packed / scale)
        hidden = np.tanh(self.weight_1 @ coordinates + self.bias_1)
        output_coordinates = self.weight_2 @ hidden + self.bias_2
        return unpack_complex(self.output_basis @ output_coordinates) * scale

    @classmethod
    def load(
        cls,
        checkpoint_dir: Path,
        *,
        expected_operator_fingerprint: str | None = None,
    ) -> FrozenNumpyMlp:
        directory = Path(checkpoint_dir)
        manifest_path = directory / "manifest.json"
        weights_path = directory / "weights.npz"
        if not manifest_path.is_file() or not weights_path.is_file():
            raise FileNotFoundError("neural checkpoint requires manifest.json and weights.npz")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema") != CHECKPOINT_SCHEMA:
            raise ValueError("unsupported neural checkpoint schema")
        actual_checksum = sha256_file(weights_path)
        if actual_checksum != manifest.get("weights_sha256"):
            raise ValueError("neural checkpoint checksum mismatch")
        fingerprint = str(manifest.get("operator_fingerprint", ""))
        if expected_operator_fingerprint is not None and fingerprint != expected_operator_fingerprint:
            raise ValueError("neural checkpoint operator fingerprint mismatch")
        with np.load(weights_path, allow_pickle=False) as payload:
            required = {
                "input_basis",
                "output_basis",
                "weight_1",
                "bias_1",
                "weight_2",
                "bias_2",
            }
            if set(payload.files) != required:
                raise ValueError("neural checkpoint array contract mismatch")
            arrays = {key: payload[key] for key in required}
        return cls(
            **arrays,
            operator_fingerprint=fingerprint,
            checkpoint_sha256=actual_checksum,
        )


class NeuralLocalSlabSolver:
    """Frozen NN local inverse with residual checks and explicit fallback."""

    def __init__(
        self,
        operator: LocalCsrOperator,
        model: FrozenNumpyMlp,
        *,
        fallback: LocalSlabSolver | None = None,
        residual_ratio_limit: float = 0.95,
        output_norm_ratio_limit: float = 1.0e6,
    ) -> None:
        if model.operator_fingerprint != operator.fingerprint:
            raise ValueError("model was not trained for this local operator")
        if model.packed_size != 2 * operator.shape[1]:
            raise ValueError("model output size does not match local operator")
        if residual_ratio_limit <= 0.0 or output_norm_ratio_limit <= 0.0:
            raise ValueError("neural safety limits must be positive")
        self.operator = operator
        self.model = model
        self.fallback = fallback
        self.residual_ratio_limit = float(residual_ratio_limit)
        self.output_norm_ratio_limit = float(output_norm_ratio_limit)
        self.apply_count = 0
        self.fallback_count = 0
        self.inference_elapsed_s = 0.0
        self.residual_check_elapsed_s = 0.0
        self.local_residual_ratios: list[float] = []
        self._destroyed = False

    def _candidate(self, rhs: np.ndarray) -> tuple[np.ndarray | None, float]:
        started = time.perf_counter()
        try:
            candidate = np.asarray(self.model.predict(rhs), dtype=np.complex128)
        except Exception:
            self.inference_elapsed_s += time.perf_counter() - started
            return None, float("inf")
        self.inference_elapsed_s += time.perf_counter() - started
        rhs_norm = max(float(np.linalg.norm(rhs)), TINY)
        if (
            candidate.shape != rhs.shape
            or not np.all(np.isfinite(candidate))
            or float(np.linalg.norm(candidate)) > self.output_norm_ratio_limit * rhs_norm
        ):
            return None, float("inf")
        started = time.perf_counter()
        ratio = relative_local_residual(self.operator, rhs, candidate)
        self.residual_check_elapsed_s += time.perf_counter() - started
        return candidate, ratio

    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None:
        if self._destroyed:
            raise RuntimeError("neural local solver has been destroyed")
        source = np.asarray(rhs, dtype=np.complex128)
        if source.shape != (self.operator.shape[1],) or out.shape != source.shape:
            raise ValueError("neural local rhs/output shape mismatch")
        candidate, ratio = self._candidate(source)
        self.apply_count += 1
        self.local_residual_ratios.append(float(ratio))
        if candidate is not None and ratio <= self.residual_ratio_limit:
            out[:] = candidate
            return
        self.fallback_count += 1
        if self.fallback is None:
            raise RuntimeError(
                "neural local solve failed safety checks and no fallback is configured"
            )
        self.fallback.solve(source, out)

    @property
    def diagnostics(self) -> dict[str, Any]:
        ratios = np.asarray(self.local_residual_ratios, dtype=float)
        finite = ratios[np.isfinite(ratios)]
        return {
            "identity": "neural",
            "apply_count": self.apply_count,
            "fallback_count": self.fallback_count,
            "fallback_fraction": self.fallback_count / max(self.apply_count, 1),
            "local_rho_median": float(np.median(finite)) if finite.size else None,
            "local_rho_p95": float(np.quantile(finite, 0.95)) if finite.size else None,
            "inference_elapsed_s": self.inference_elapsed_s,
            "residual_check_elapsed_s": self.residual_check_elapsed_s,
            "model_storage_bytes": self.model.storage_bytes,
            "checkpoint_sha256": self.model.checkpoint_sha256,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        if self.fallback is not None:
            self.fallback.destroy()
        self._destroyed = True


class IluNeuralCorrectionSlabSolver(NeuralLocalSlabSolver):
    """Lane B: accept an NN correction only when it does not degrade ILU."""

    def __init__(
        self,
        operator: LocalCsrOperator,
        model: FrozenNumpyMlp,
        ilu_solver: LocalSlabSolver,
        *,
        residual_ratio_limit: float = 0.95,
        nondegradation_tolerance: float = 1.0e-12,
    ) -> None:
        super().__init__(
            operator,
            model,
            fallback=None,
            residual_ratio_limit=residual_ratio_limit,
        )
        self.ilu_solver = ilu_solver
        self.nondegradation_tolerance = float(nondegradation_tolerance)

    def solve(self, rhs: np.ndarray, out: np.ndarray) -> None:
        if self._destroyed:
            raise RuntimeError("ILU+NN local solver has been destroyed")
        source = np.asarray(rhs, dtype=np.complex128)
        baseline = np.empty_like(source)
        self.ilu_solver.solve(source, baseline)
        baseline_ratio = relative_local_residual(self.operator, source, baseline)
        residual = source - self.operator.action(baseline)
        delta, correction_ratio = self._candidate(residual)
        self.apply_count += 1
        if delta is None:
            candidate_ratio = float("inf")
        else:
            candidate = baseline + delta
            candidate_ratio = relative_local_residual(self.operator, source, candidate)
        self.local_residual_ratios.append(float(candidate_ratio))
        if (
            delta is not None
            and correction_ratio <= self.residual_ratio_limit
            and candidate_ratio <= baseline_ratio * (1.0 + self.nondegradation_tolerance)
        ):
            out[:] = baseline + delta
            return
        self.fallback_count += 1
        out[:] = baseline

    @property
    def diagnostics(self) -> dict[str, Any]:
        result = super().diagnostics
        result["identity"] = "ilu_neural_correction"
        result["ilu"] = self.ilu_solver.diagnostics
        return result

    def destroy(self) -> None:
        if self._destroyed:
            return
        self.ilu_solver.destroy()
        self._destroyed = True
