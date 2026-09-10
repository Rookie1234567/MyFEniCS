"""Small, bounded GCROT recycling kernel for the opt-in V8 I4 profile.

The kernel deliberately has one numerical entry point: one call to the local
SciPy ``gcrotmk`` implementation with ``m=k=8`` and ``maxiter=1``. It keeps
only a model-local list of verified ``(U, Q)`` pairs, where ``A4 U = Q`` and
``Q.conj().T @ Q`` is the identity. PETSc ownership and the V7 admission
policy live in :mod:`physical_bounded_policy`.

SciPy mutates the ``CU`` list that it receives. Every solve therefore works
on private copies of the persistent pairs. A candidate is committed only
after its finite/rank/orthogonality/closure checks, its final native residual,
and the input/constraint checks have all completed.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import time
from typing import Any, Callable, Iterable

import numpy as np


MAX_POOL_PAIRS = 8
GCROT_M = 8
GCROT_K = 8
GCROT_MAXITER = 1
GCROT_TOL = 1.0e-4
GCROT_ATOL = 0.0
MAX_NEW_B4 = 16
MAX_NEW_DIRECTIONS = 16
ORTHOGONALITY_LIMIT = 1.0e-10
CLOSURE_LIMIT = 1.0e-10
RANK_THRESHOLD = 1.0e-12
NATIVE_SPOT_INTERVAL = 32
RECYCLING_EXTRA_BYTES_LIMIT = 64 * 1024**2
# The transient count is listed separately from the V/Z basis in the phase
# ledger below; the V/Z count itself depends on SciPy's current ``ml``.
SCIPY_INNER_TRANSIENT_VECTOR_COUNT = 4
# During ``truncate='smallest'`` SciPy keeps the old and newly assembled
# CU columns alive while it forms the retained k-1 columns.  Count both
# vector matrices explicitly; this is separate from the V/Z basis below.
SCIPY_SMALLEST_CU_OVERLAP_VECTOR_COUNT = 2 * (GCROT_K - 1)
SCIPY_SMALL_MATRIX_BYTES = 4 * (GCROT_M + 2) * (GCROT_K + 2) * 16
# The finalized p4 owner map has 48960 independent rows.  This is a derived
# numeric payload bound, not a claim about the live allocator peak or RSS.
P4_INDEPENDENT_ROWS = 48960
POOL_NUMERIC_BYTES_P4_DERIVED = 2 * P4_INDEPENDENT_ROWS * MAX_POOL_PAIRS * 16


class RecycledI4Error(RuntimeError):
    """Base class for an invalid recycled I4 operation or candidate."""


class RecycledI4SafetyStop(RecycledI4Error):
    """A callback-visible safety deadline interrupted the library call."""

    def __init__(self, reason: str, *, hard: bool = False):
        self.reason = str(reason)
        self.hard = bool(hard)
        super().__init__(self.reason)


class RecycledI4WorkLimit(RecycledI4Error):
    """The fixed per-RHS B4/direction budget was reached."""

    def __init__(self, reason: str = "new B4/direction work cap exceeded"):
        self.reason = str(reason)
        super().__init__(self.reason)


class _PoolCandidateRejected(RecycledI4Error):
    """A finite candidate failed a non-rank pool gate.

    Rank deficiency is handled by the rank-revealing selector and is not
    represented by this exception. All other failures propagate to the
    caller so malformed or physically invalid candidates cannot silently turn
    into a successful admission.
    """

    def __init__(self, reason: str, facts: dict[str, Any] | None = None):
        self.reason = str(reason)
        self.facts = dict(facts or {})
        super().__init__(self.reason)


def _canonical_identity(identity: Any) -> str:
    if identity is None:
        raise ValueError("model identity must not be null")
    if isinstance(identity, str):
        value = identity.strip()
        if not value or value.lower() in {"none", "null"}:
            raise ValueError("model identity must not be empty")
        return value
    try:
        value = json.dumps(identity, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("model identity must be JSON-serializable and finite") from exc
    if not value:
        raise ValueError("model identity must not be empty")
    return value


def _identity_digest(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def gcrotmk_backend_facts() -> dict[str, Any]:
    """Capture the installed GCROT signature and source identity."""

    import scipy
    from scipy.sparse.linalg import gcrotmk

    source = inspect.getsourcefile(gcrotmk)
    source_path = Path(source).resolve() if source is not None else None
    required = {"tol", "maxiter", "m", "k", "CU", "discard_C",
                "truncate", "atol"}
    signature = inspect.signature(gcrotmk)
    missing = sorted(required.difference(signature.parameters))
    if missing:
        raise RuntimeError(f"installed gcrotmk lacks required parameters: {missing}")
    source_sha = None
    if source_path is not None and source_path.is_file():
        source_sha = hashlib.sha256(source_path.read_bytes()).hexdigest()
    return dict(
        backend="scipy.sparse.linalg.gcrotmk",
        scipy_version=str(scipy.__version__),
        source_path=str(source_path) if source_path is not None else None,
        source_sha256=source_sha,
        signature=str(signature),
        required_parameters=sorted(required),
    )


def _vector(value: Any, *, name: str, copy: bool = False) -> np.ndarray:
    try:
        array = np.array(value, dtype=None, copy=copy)
    except (TypeError, ValueError) as exc:
        raise RecycledI4Error(f"{name} is not an array") from exc
    if array.ndim != 1 or array.dtype != np.dtype(np.complex128):
        raise RecycledI4Error(f"{name} must be a one-dimensional complex128 array")
    if not np.isfinite(array).all():
        raise RecycledI4Error(f"{name} contains non-finite values")
    return array


def _norm(value: np.ndarray) -> float:
    result = float(np.linalg.norm(value))
    if not np.isfinite(result):
        raise RecycledI4Error("non-finite vector norm")
    return result


def _relative(numerator: float, denominator: float) -> float:
    return float(numerator / max(float(denominator), np.finfo(float).tiny))


def _pair_bytes(pairs: Iterable[tuple[np.ndarray, np.ndarray]], *,
                include_terminal: bool = False) -> int:
    # A SciPy CU workspace also contains the terminal ``(None, x.copy())``
    # solution snapshot. It is temporary workspace, not retained recycling
    # payload, but it is included in the live-workspace bound when requested.
    total = 0
    for first, second in pairs:
        if first is None:
            if include_terminal and second is not None:
                total += second.nbytes
        elif second is not None:
            total += first.nbytes + second.nbytes
    return int(total)


def _constraint_passes(checker: Callable[[np.ndarray], Any] | None,
                       value: np.ndarray, *, name: str) -> None:
    if checker is None:
        return
    verdict = checker(np.array(value, copy=True))
    if isinstance(verdict, dict):
        verdict = verdict.get("passed", False)
    if not isinstance(verdict, (bool, np.bool_)) or not bool(verdict):
        raise _PoolCandidateRejected(f"constraint check failed for {name}")


class VerifiedRecyclingPool:
    """A model-bound pool of at most eight verified ``(U, Q)`` pairs.

    ``pairs()`` returns ``(U, Q)``. SciPy receives the reversed ``(Q, U)``
    representation through :meth:`working_cu`; neither representation aliases
    persistent storage during a library call.
    """

    def __init__(self, model_identity: Any, *, max_pairs: int = MAX_POOL_PAIRS):
        if not 0 <= int(max_pairs) <= MAX_POOL_PAIRS:
            raise ValueError(f"max_pairs must be between zero and {MAX_POOL_PAIRS}")
        self.identity = _canonical_identity(model_identity)
        self.identity_sha256 = _identity_digest(self.identity)
        self.max_pairs = int(max_pairs)
        self._pairs: list[tuple[np.ndarray, np.ndarray]] = []
        self._closure_errors: list[float] = []
        self.destroyed = False
        self.replacements = 0

    @property
    def size(self) -> int:
        return len(self._pairs)

    @property
    def retained_bytes(self) -> int:
        return _pair_bytes(self._pairs)

    @property
    def closure_errors(self) -> list[float]:
        if self.destroyed:
            raise RecycledI4Error("recycling pool has been released")
        return list(self._closure_errors)

    def pairs(self, *, copy: bool = True) -> list[tuple[np.ndarray, np.ndarray]]:
        if self.destroyed:
            raise RecycledI4Error("recycling pool has been released")
        if copy:
            return [(u.copy(), q.copy()) for u, q in self._pairs]
        return list(self._pairs)

    def working_cu(self) -> list[tuple[np.ndarray, np.ndarray]]:
        """Return one private SciPy ``(Q, U)`` workspace."""

        if self.destroyed:
            raise RecycledI4Error("recycling pool has been released")
        return [(q.copy(), u.copy()) for u, q in self._pairs]

    def replace(self, pairs: Iterable[tuple[np.ndarray, np.ndarray]],
                *, closure_errors: Iterable[float] | None = None) -> None:
        """Copy externally supplied ``(U, Q)`` pairs transactionally."""

        if self.destroyed:
            raise RecycledI4Error("recycling pool has been released")
        materialized = list(pairs)
        committed = [(
            _vector(u, name="pool U", copy=True),
            _vector(q, name="pool Q", copy=True),
        ) for u, q in materialized]
        values = ([0.0] * len(committed) if closure_errors is None
                  else list(closure_errors))
        errors = [float(value) for value in values]
        self._commit_owned([(q, u) for u, q in committed], errors)

    def _commit_owned(self, cu_pairs: list[tuple[np.ndarray, np.ndarray]],
                      closure_errors: list[float]) -> None:
        """Commit validated SciPy workspace arrays without another copy."""

        if self.destroyed:
            raise RecycledI4Error("recycling pool has been released")
        if len(cu_pairs) != len(closure_errors):
            raise RecycledI4Error("pool closure metadata length differs")
        if len(cu_pairs) > self.max_pairs:
            raise RecycledI4Error("recycling pool capacity exceeded")
        retained = _pair_bytes(cu_pairs)
        if retained > RECYCLING_EXTRA_BYTES_LIMIT:
            raise RecycledI4Error(
                f"recycling pool exceeds {RECYCLING_EXTRA_BYTES_LIMIT} bytes")
        for index, (q, u) in enumerate(cu_pairs):
            _vector(q, name=f"pool candidate Q[{index}]")
            _vector(u, name=f"pool candidate U[{index}]")
            if q.shape != u.shape:
                raise RecycledI4Error(f"pool candidate pair {index} has mismatched shape")
            error = float(closure_errors[index])
            if not np.isfinite(error) or error > CLOSURE_LIMIT:
                raise RecycledI4Error(f"pool candidate pair {index} has invalid closure metadata")
        # The assignment is the transaction boundary. The old pool remains
        # untouched until every new array and metadata item has passed above.
        self._pairs = [(u, q) for q, u in cu_pairs]
        self._closure_errors = list(closure_errors)
        self.replacements += 1

    def reset(self) -> None:
        if self.destroyed:
            raise RecycledI4Error("recycling pool has been released")
        self._pairs.clear()
        self._closure_errors.clear()

    def snapshot(self) -> dict[str, Any]:
        return dict(
            model_identity_sha256=self.identity_sha256,
            max_pairs=self.max_pairs,
            pairs=len(self._pairs),
            retained_bytes=self.retained_bytes,
            retained_bytes_limit=RECYCLING_EXTRA_BYTES_LIMIT,
            closure_errors=list(self._closure_errors),
            replacements=self.replacements,
            destroyed=self.destroyed,
        )

    def destroy(self) -> None:
        if not self.destroyed:
            self._pairs.clear()
            self._closure_errors.clear()
            self.destroyed = True


class _Deadline:
    def __init__(self, *, sample: Callable[[], Any], stop_requested: Callable[[], bool],
                 clock: Callable[[], float], started: float,
                 safe_seconds: float, hard_seconds: float):
        self.sample = sample
        self.stop_requested = stop_requested
        self.clock = clock
        self.started = started
        self.safe_seconds = float(safe_seconds)
        self.hard_seconds = float(hard_seconds)

    def check(self, where: str) -> None:
        # Both callbacks are inside the library call, so checking only SciPy's
        # outer callback would miss a long physical A4 or B4 operation.
        self.sample()
        if bool(self.stop_requested()):
            raise RecycledI4SafetyStop("OUTER_SAFE_DEADLINE")
        elapsed = float(self.clock() - self.started)
        if not np.isfinite(elapsed):
            raise RecycledI4Error(f"non-finite elapsed time at {where}")
        if elapsed >= self.hard_seconds:
            raise RecycledI4SafetyStop("I4_HARD_TIME_EXCEEDED", hard=True)
        if elapsed >= self.safe_seconds:
            raise RecycledI4SafetyStop("I4_SAFE_RETURN_REQUESTED")


class BoundedGCROTI4:
    """Run one bounded GCROT round and maintain a verified local pool."""

    def __init__(
        self,
        action: Callable[[np.ndarray], np.ndarray],
        pc: Callable[[np.ndarray], np.ndarray],
        *,
        model_identity: Any,
        validation_action: Callable[[np.ndarray], np.ndarray] | None = None,
        constraint_check: Callable[[np.ndarray], Any] | None = None,
        q_constraint_check: Callable[[np.ndarray], Any] | None = None,
        u_constraint_check: Callable[[np.ndarray], Any] | None = None,
        sample: Callable[[], Any] = lambda: None,
        stop_requested: Callable[[], bool] = lambda: False,
        pool: VerifiedRecyclingPool | None = None,
        target: float = GCROT_TOL,
        safe_seconds: float = 25.0,
        hard_seconds: float = 30.0,
        clock: Callable[[], float] | None = None,
    ):
        if float(target) != GCROT_TOL:
            raise ValueError("recycled I4 fixes the 1e-4 inner target")
        if not np.isfinite(safe_seconds) or safe_seconds <= 0:
            raise ValueError("safe_seconds must be finite and positive")
        if not np.isfinite(hard_seconds) or hard_seconds < safe_seconds:
            raise ValueError("hard_seconds must be no shorter than safe_seconds")
        self.action = action
        self.pc = pc
        self.validation_action = action if validation_action is None else validation_action
        # Q is the dual/image side and U is the primal/recycling side. Keep
        # their gates separate; the legacy single checker remains a convenient
        # compatibility default for pure-array callers.
        self.q_constraint_check = (constraint_check if q_constraint_check is None
                                   else q_constraint_check)
        self.u_constraint_check = (constraint_check if u_constraint_check is None
                                   else u_constraint_check)
        self.sample = sample
        self.stop_requested = stop_requested
        self.target = float(target)
        self.safe_seconds = float(safe_seconds)
        self.hard_seconds = float(hard_seconds)
        self.clock = time.monotonic if clock is None else clock
        canonical = _canonical_identity(model_identity)
        if pool is None:
            pool = VerifiedRecyclingPool(canonical)
        if pool.identity != canonical:
            raise ValueError("recycling pool model identity differs")
        self.pool = pool
        # Capture once; re-inspecting and re-hashing the backend for every RHS
        # would be needless setup work.
        self.backend = gcrotmk_backend_facts()
        self.calls = 0
        self.destroyed = False
        self._native_spot_seen = False
        self._last_native_spot_call = 0
        self._exit_native_spot_checks = 0
        self._last_exit_native_spot: dict[str, Any] = {}

    def reset(self, model_identity: Any | None = None) -> None:
        if self.destroyed:
            raise RecycledI4Error("recycled I4 has been released")
        if model_identity is not None and _canonical_identity(model_identity) != self.pool.identity:
            raise ValueError("cannot reset a pool for a different model identity")
        self.pool.reset()
        self._native_spot_seen = False
        self._last_native_spot_call = 0
        self._exit_native_spot_checks = 0
        self._last_exit_native_spot = {}

    def snapshot(self) -> dict[str, Any]:
        return dict(
            calls=self.calls,
            backend=self.backend,
            pool=self.pool.snapshot(),
            native_spot=dict(seen=self._native_spot_seen,
                             last_call=self._last_native_spot_call,
                             interval=NATIVE_SPOT_INTERVAL),
            exit_native_spot=dict(checks=self._exit_native_spot_checks,
                                  last=dict(self._last_exit_native_spot)),
            fixed=dict(m=GCROT_M, k=GCROT_K, maxiter=GCROT_MAXITER,
                        truncate="smallest", discard_C=False,
                        tol=GCROT_TOL, atol=GCROT_ATOL,
                        max_new_B4=MAX_NEW_B4,
                        max_new_directions=MAX_NEW_DIRECTIONS,
                        extra_bytes_limit=RECYCLING_EXTRA_BYTES_LIMIT),
        )

    def destroy(self) -> None:
        if not self.destroyed:
            self.pool.destroy()
            self.destroyed = True

    def native_exit_spot_check(self) -> dict[str, Any]:
        """Check every retained pair once before releasing the auxiliary stack."""

        if self.destroyed:
            raise RecycledI4Error("recycled I4 has been released")
        pairs = self.pool.pairs(copy=True)
        errors = []
        attempted = completed = 0
        started = time.perf_counter()
        failure: BaseException | None = None
        try:
            for index, (u, q) in enumerate(pairs):
                # The resource callback is deliberately checked on both sides
                # of each native action.  A stop signal therefore prevents a
                # later audit column from being forced merely to complete the
                # accounting record.
                self.sample()
                _constraint_passes(self.u_constraint_check, u,
                                   name=f"exit U[{index}]")
                _constraint_passes(self.q_constraint_check, q,
                                   name=f"exit Q[{index}]")
                attempted += 1
                image = _vector(self.validation_action(u.copy()),
                                name=f"exit native A4 action[{index}]", copy=False)
                if image.shape != u.shape:
                    raise RecycledI4Error(f"exit native A4 action[{index}] has wrong shape")
                completed += 1
                error = _relative(np.linalg.norm(image - q), np.linalg.norm(q))
                if not np.isfinite(error) or error > CLOSURE_LIMIT:
                    raise _PoolCandidateRejected("exit_native_A4U_closure", dict(
                        closure_error=float(error), limit=CLOSURE_LIMIT, index=index))
                errors.append(float(error))
                self.sample()
        except BaseException as exc:
            failure = exc
            raise
        finally:
            elapsed = float(time.perf_counter() - started)
            facts = dict(
                checked=completed, pairs=len(pairs), errors=list(errors),
                maximum_error=max(errors, default=0.0), limit=CLOSURE_LIMIT,
                attempted_native_A4=int(attempted), completed_native_A4=int(completed),
                elapsed_seconds=elapsed,
                status="aborted" if failure is not None else "completed",
                exception_type=None if failure is None else type(failure).__name__,
                pool_identity_sha256=self.pool.identity_sha256,
                input_unchanged=True,
            )
            self._exit_native_spot_checks += completed
            self._last_exit_native_spot = facts
        return facts

    @staticmethod
    def _candidate_pairs(working: list[tuple[Any, Any]]) -> list[tuple[np.ndarray, np.ndarray]]:
        pairs: list[tuple[np.ndarray, np.ndarray]] = []
        for index, pair in enumerate(working):
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise RecycledI4Error(f"CU pair {index} is malformed")
            q, u = pair
            # SciPy appends (None, x.copy()) after each call. It is a solution
            # snapshot, not an A4 image, so it is discarded after validating its
            # finite vector shape. No other unpaired object is accepted.
            if q is None:
                if u is None:
                    raise RecycledI4Error("CU contains an unpaired null direction")
                _vector(u, name="CU terminal solution")
                continue
            if u is None:
                raise RecycledI4Error("CU contains a direction without Q")
            q_array = _vector(q, name=f"CU Q[{index}]")
            u_array = _vector(u, name=f"CU U[{index}]")
            if q_array.shape != u_array.shape:
                raise RecycledI4Error(f"CU pair {index} has mismatched shape")
            pairs.append((q_array, u_array))
        return pairs

    @staticmethod
    def _rank_revealing_subset(
        pairs: list[tuple[np.ndarray, np.ndarray]],
    ) -> tuple[list[tuple[np.ndarray, np.ndarray]], list[int], int, list[float]]:
        if not pairs:
            return [], [], 0, []
        from scipy.linalg import qr

        q_matrix = np.column_stack([q for q, _ in pairs])
        _, r_factor, pivots = qr(q_matrix, mode="economic", pivoting=True,
                                 check_finite=False)
        diagonal = np.abs(np.diag(r_factor))
        scale = max(float(diagonal[0]) if diagonal.size else 0.0,
                    np.finfo(float).tiny)
        threshold = RANK_THRESHOLD * scale
        rank = int(np.count_nonzero(diagonal > threshold))
        # Preserve CU order after using pivoted QR only to choose independent
        # paired columns. No U column is re-associated with another Q column.
        selected = sorted(int(index) for index in pivots[:rank])
        return [pairs[index] for index in selected], selected, rank, diagonal.tolist()

    def _validate_pool_candidate(
        self,
        pairs: list[tuple[np.ndarray, np.ndarray]],
        *,
        inherited_closure_error: float,
        completed_new_directions: int,
        call_number: int,
        invoke_cached: Callable[[np.ndarray], np.ndarray],
        invoke_native: Callable[[np.ndarray], np.ndarray],
        native_spot_due: bool,
    ) -> tuple[dict[str, Any], list[tuple[np.ndarray, np.ndarray]]]:
        if len(pairs) > self.pool.max_pairs:
            raise _PoolCandidateRejected("pool_capacity", {"candidate_pairs": len(pairs)})
        for index, (q, u) in enumerate(pairs):
            _vector(q, name=f"candidate Q[{index}]")
            _vector(u, name=f"candidate U[{index}]")
            if q.shape != u.shape:
                raise _PoolCandidateRejected("pair_shape", {"index": index})
            _constraint_passes(self.q_constraint_check, q, name=f"candidate Q[{index}]")
            _constraint_passes(self.u_constraint_check, u, name=f"candidate U[{index}]")

        all_q_matrix = (np.column_stack([q for q, _ in pairs])
                        if pairs else np.empty((0, 0), dtype=np.complex128))
        all_singular_values = np.linalg.svd(
            all_q_matrix, compute_uv=False) if pairs else np.empty(0, dtype=float)
        if not np.isfinite(all_singular_values).all():
            raise _PoolCandidateRejected("rank_spectrum_nonfinite")
        selected, selected_indices, rank, residual_norms = self._rank_revealing_subset(pairs)
        # A linearly dependent CU column is the only candidate condition that
        # may be pruned. The surviving columns must already be orthonormal;
        # silently repairing a non-orthogonal library result would hide a real
        # numerical or ABI error.
        if selected:
            q_matrix = np.column_stack([q for q, _ in selected])
            q_gram = q_matrix.conj().T @ q_matrix
            gram_error = float(np.linalg.norm(
                q_gram - np.eye(rank, dtype=np.complex128),
                ord=2))
            if not np.isfinite(gram_error) or gram_error > ORTHOGONALITY_LIMIT:
                raise _PoolCandidateRejected("orthogonality", dict(
                    orthogonality_error=gram_error, limit=ORTHOGONALITY_LIMIT,
                    rank=rank, candidate_pairs=len(pairs)))
        else:
            gram_error = 0.0
            q_gram = np.empty((0, 0), dtype=np.complex128)

        # The last non-tail CU pair is the one newly generated by this single
        # GCROT outer round. Older pairs inherit the already verified A4U=Q
        # relation through SciPy's linear QR/truncation transforms. Its cached
        # A4 image is checked directly; native A4 is sampled only on the first
        # nonempty pool and then every 32nd I4 call.
        closure_errors: list[float] = []
        new_pair_index = len(pairs) - 1 if completed_new_directions > 0 and pairs else None
        for selected_index, (q, u) in zip(selected_indices, selected, strict=True):
            if selected_index == new_pair_index:
                image = invoke_cached(u)
                error = _relative(np.linalg.norm(image - q), np.linalg.norm(q))
                if not np.isfinite(error) or error > CLOSURE_LIMIT:
                    raise _PoolCandidateRejected("A4U_closure", dict(
                        closure_error=float(error), limit=CLOSURE_LIMIT,
                        source="cached_A4", index=selected_index))
            else:
                error = float(inherited_closure_error)
                if not np.isfinite(error) or error > CLOSURE_LIMIT:
                    raise _PoolCandidateRejected("inherited_A4U_closure", dict(
                        closure_error=error, limit=CLOSURE_LIMIT,
                        source="inherited_pool", index=selected_index))
            closure_errors.append(float(error))

        native_checked = 0
        native_errors: list[float] = []
        if native_spot_due:
            for index, (q, u) in enumerate(selected):
                # ``selected`` is bounded by MAX_POOL_PAIRS, so this remains a
                # finite validation operation.
                image = invoke_native(u)
                error = _relative(np.linalg.norm(image - q), np.linalg.norm(q))
                if not np.isfinite(error) or error > CLOSURE_LIMIT:
                    raise _PoolCandidateRejected("native_A4U_closure", dict(
                        closure_error=float(error), limit=CLOSURE_LIMIT, index=index))
                native_errors.append(float(error))
                native_checked += 1

        return dict(
            candidate_pairs=len(pairs),
            pairs=rank,
            rank=rank,
            rank_threshold=RANK_THRESHOLD,
            rank_pruned=len(pairs) - rank,
            rank_residual_norms=residual_norms,
            rank_singular_values=all_singular_values,
            q_gram=q_gram,
            orthogonality_error=float(gram_error),
            orthogonality_limit=ORTHOGONALITY_LIMIT,
            closure_errors=closure_errors,
            closure_error=max(closure_errors, default=0.0),
            closure_limit=CLOSURE_LIMIT,
            cached_closure_checks=1 if new_pair_index in selected_indices else 0,
            native_spot_checked=native_checked,
            native_spot_errors=native_errors,
            native_spot_due=bool(native_spot_due),
            native_spot_call=call_number if native_checked else None,
            inherited_closure_error=float(inherited_closure_error),
        ), selected

    def _memory_facts(self, *, pool_before: int, pool_before_bytes: int,
                      working: list[tuple[Any, Any]], rhs: np.ndarray,
                      projection: np.ndarray, projection_matrix_bytes: int,
                      inner_dimension: int, pool_after_bytes: int) -> dict[str, Any]:
        working_bytes = _pair_bytes(working, include_terminal=True)
        vector_bytes = int(rhs.nbytes)
        inner_vz_vectors = 2 * int(inner_dimension) + 1
        inner_vz_bytes = inner_vz_vectors * vector_bytes
        inner_transient_bytes = SCIPY_INNER_TRANSIENT_VECTOR_COUNT * vector_bytes
        inner_krylov_bytes = inner_vz_bytes + inner_transient_bytes
        smallest_cu_overlap_bytes = int(
            SCIPY_SMALLEST_CU_OVERLAP_VECTOR_COUNT if pool_before else 0) * vector_bytes
        # The bounds intentionally include both sides of the array operations:
        # a conservative N-by-k QR input/output pair and the conjugate N-by-k
        # Gram input plus its k-by-k result.  These are small, fixed phase
        # terms and do not rely on a solver-reported ``cap_passed`` flag.
        qr_input_output_bytes = (2 * MAX_POOL_PAIRS * vector_bytes
                                 if pool_before else 0)
        gram_conjugate_temp_bytes = (
            MAX_POOL_PAIRS * vector_bytes + MAX_POOL_PAIRS * MAX_POOL_PAIRS * 16
            if pool_before else 0)
        ordinary_vectors_bytes = int(rhs.nbytes + projection.nbytes + 5 * vector_bytes)
        base_extra = int(pool_before_bytes + working_bytes)
        # The q/u matrices used for the initial projection are released before
        # entering SciPy. The phases therefore have separate named bounds;
        # adding both would overstate a peak while omitting either would hide a
        # live allocation. The V/Z count follows _fgmres; the transient count
        # covers r/w/cx/ux. CU reorthogonalization and the small QR/SVD/Gram
        # work are kept as separate conservative terms.
        inner_vectors = inner_vz_vectors + SCIPY_INNER_TRANSIENT_VECTOR_COUNT
        library_scratch = (smallest_cu_overlap_bytes + qr_input_output_bytes +
                           gram_conjugate_temp_bytes + SCIPY_SMALL_MATRIX_BYTES)
        projection_extra = (base_extra + int(projection_matrix_bytes) +
                            SCIPY_SMALL_MATRIX_BYTES)
        gcrot_extra = base_extra + library_scratch
        candidate_q_matrix = MAX_POOL_PAIRS * vector_bytes
        candidate_extra = (base_extra + candidate_q_matrix +
                           qr_input_output_bytes + gram_conjugate_temp_bytes +
                           SCIPY_SMALL_MATRIX_BYTES)
        extra_peak = max(projection_extra, gcrot_extra, candidate_extra)
        projection_phase = projection_extra + ordinary_vectors_bytes
        library_phase = gcrot_extra + ordinary_vectors_bytes + inner_krylov_bytes
        candidate_phase = candidate_extra + ordinary_vectors_bytes
        full_peak = max(projection_phase, library_phase, candidate_phase)
        return dict(
            retained_bytes=int(pool_after_bytes),
            persistent_before_bytes=int(pool_before_bytes),
            working_cu_bytes_including_terminal=int(working_bytes),
            projection_matrix_bytes=int(projection_matrix_bytes),
            inner_dimension=int(inner_dimension),
            inner_vz_vector_count=int(inner_vz_vectors),
            base_inner_vz_bytes=int(inner_vz_bytes),
            inner_transient_vector_bytes=int(inner_transient_bytes),
            base_inner_krylov_bytes=int(inner_krylov_bytes),
            ordinary_live_vector_bytes=int(ordinary_vectors_bytes),
            extra_recycling_peak_bytes=int(extra_peak),
            extra_recycling_cap_passed=bool(extra_peak <= RECYCLING_EXTRA_BYTES_LIMIT),
            named_array_bytes=dict(
                persistent_pool=int(pool_before_bytes),
                cu_workspace_including_terminal=int(working_bytes),
                rhs=int(rhs.nbytes), projection=int(projection.nbytes),
                projection_q_u_matrices=int(projection_matrix_bytes),
                candidate_q_matrix_bound=int(candidate_q_matrix),
            ),
            scipy_inner_vz_vector_count=int(inner_vz_vectors),
            scipy_inner_transient_vector_count=SCIPY_INNER_TRANSIENT_VECTOR_COUNT,
            scipy_smallest_cu_overlap_vector_count=int(
                SCIPY_SMALLEST_CU_OVERLAP_VECTOR_COUNT if pool_before else 0),
            scipy_smallest_cu_overlap_bytes=int(smallest_cu_overlap_bytes),
            scipy_qr_input_output_bytes=int(qr_input_output_bytes),
            scipy_gram_conjugate_temp_bytes=int(gram_conjugate_temp_bytes),
            scipy_scratch_vector_count=inner_vectors,
            scipy_scratch_bound=int(library_scratch),
            scipy_small_matrix_bound=int(SCIPY_SMALL_MATRIX_BYTES),
            phase_bounds=dict(projection_phase=int(projection_phase),
                              gcrot_phase=int(library_phase),
                              candidate_validation_phase=int(candidate_phase),
                              base_inner_vz_bytes=int(inner_vz_bytes),
                              inner_transient_bytes=int(inner_transient_bytes),
                              smallest_cu_overlap_bytes=int(smallest_cu_overlap_bytes),
                              qr_input_output_bytes=int(qr_input_output_bytes),
                              gram_conjugate_temp_bytes=int(gram_conjugate_temp_bytes)),
            peak_live_bytes=int(full_peak),
            cap_bytes=RECYCLING_EXTRA_BYTES_LIMIT,
            cap_passed=bool(extra_peak <= RECYCLING_EXTRA_BYTES_LIMIT),
            p4_reference_numeric_bytes=POOL_NUMERIC_BYTES_P4_DERIVED,
            classification=("conservative_named_arrays_plus_pinned_SciPy_1.11.4_"
                            "m8k8_vector_scratch; excludes physical action workspace"),
        )

    def _facts(
        self,
        *,
        call_number: int,
        counters: dict[str, int],
        pool_before: int,
        pool_after: int,
        rhs_norm: float,
        absolute: float,
        relative: float,
        elapsed: float,
        status: str,
        reason: Any,
        stop_reason: str,
        requested_safe_return: bool,
        timeout_exceeded: bool,
        library_info: Any,
        projection_pre: float | None,
        projection_post: float | None,
        projection_coefficients: np.ndarray,
        projection_norm: float,
        pool_update: str,
        pool_facts: dict[str, Any],
        memory: dict[str, Any],
        legal_direction_count: int,
        usable_new_directions: int,
    ) -> dict[str, Any]:
        return dict(
            status=status,
            quality_label=status,
            target=GCROT_TOL,
            final_true_residual=relative,
            residual_absolute=absolute,
            eps_norm=absolute,
            rhs_norm=rhs_norm,
            iterations=int(counters["completed_new_arnoldi_directions"]),
            gcrot_outer_iterations=1 if library_info is not None else 0,
            gcrot_inner_dimension=int(memory["inner_dimension"]),
            reason=reason,
            library_info=library_info,
            restart=GCROT_M,
            max_it=GCROT_MAXITER,
            m=GCROT_M,
            k=GCROT_K,
            truncate="smallest",
            discard_C=False,
            tol=GCROT_TOL,
            atol=GCROT_ATOL,
            zero_start=True,
            initial_guess='library_x0_zero_plus_current_pool_projection',
            pool_projection_source='current_pool_only',
            seconds=elapsed,
            actual_elapsed_seconds=elapsed,
            requested_safe_return=bool(requested_safe_return),
            timeout_exceeded=bool(timeout_exceeded),
            stop_reason=stop_reason,
            legal_direction_count=int(legal_direction_count),
            usable_new_arnoldi_directions=int(usable_new_directions),
            A4_matvec=int(counters["A4_matvec"]),
            B4_calls=int(counters["B4_calls"]),
            explicit_A4=int(counters["explicit_A4"]),
            native_A4_checks=int(counters["native_A4_checks"]),
            pool_A4_checks=int(counters["pool_A4_checks"]),
            cached_A4_checks=int(counters["cached_A4_checks"]),
            attempted=dict(counters),
            attempted_B4=int(counters["attempted_B4"]),
            completed_B4=int(counters["B4_calls"]),
            attempted_new_arnoldi_directions=int(counters["attempted_new_arnoldi_directions"]),
            completed_new_arnoldi_directions=int(counters["completed_new_arnoldi_directions"]),
            completed_legal_new_arnoldi_directions=int(
                counters["completed_legal_new_arnoldi_directions"]),
            new_B4_calls=int(counters["B4_calls"]),
            new_arnoldi_directions=int(counters["completed_new_arnoldi_directions"]),
            pool_before=pool_before,
            pool_after=pool_after,
            pool_size=pool_after,
            pool_update=pool_update,
            pool_facts=pool_facts,
            pool_projection=dict(
                pre_relative=projection_pre,
                post_relative=projection_post,
                norm=float(projection_norm),
                coefficients_norm=float(np.linalg.norm(projection_coefficients)),
                coefficients_count=int(projection_coefficients.size),
            ),
            pool_identity_sha256=self.pool.identity_sha256,
            exit_native_spot_checks=int(self._exit_native_spot_checks),
            backend=self.backend,
            recycling_memory=memory,
            fixed_work=dict(max_new_B4=MAX_NEW_B4,
                            max_new_arnoldi_directions=MAX_NEW_DIRECTIONS),
            persistent_pool=dict(
                pairs=pool_after,
                retained_bytes=int(self.pool.retained_bytes),
                retained_bytes_limit=RECYCLING_EXTRA_BYTES_LIMIT,
            ),
            call=call_number,
        )

    def solve(self, rhs: Any) -> dict[str, Any]:
        """Solve one RHS, returning a finite native-residual-checked result."""

        if self.destroyed:
            raise RecycledI4Error("recycled I4 has been released")
        original = np.asarray(rhs)
        rhs_array = _vector(rhs, name="rhs", copy=True)
        if original.shape != rhs_array.shape or not np.array_equal(original, rhs_array):
            raise RecycledI4Error("rhs conversion changed the input")

        self.calls += 1
        call_number = self.calls
        started = float(self.clock())
        deadline = _Deadline(sample=self.sample, stop_requested=self.stop_requested,
                              clock=self.clock, started=started,
                              safe_seconds=self.safe_seconds,
                              hard_seconds=self.hard_seconds)
        rhs_norm = _norm(rhs_array)
        pool_before_pairs = self.pool.pairs(copy=True)
        pool_before = len(pool_before_pairs)
        pool_before_bytes = self.pool.retained_bytes
        inner_dimension = GCROT_M + max(GCROT_K - pool_before, 0)
        inherited_closure_error = max(self.pool.closure_errors, default=0.0)
        # The one copied pair list is both the projection input and SciPy's
        # private CU workspace. SciPy mutates it only after projection values
        # have been computed.
        working = [(q, u) for u, q in pool_before_pairs]
        counters = dict(
            A4_matvec=0, attempted_A4=0, completed_A4=0,
            explicit_A4=0, attempted_explicit_A4=0, native_A4_checks=0,
            pool_A4_checks=0, cached_A4_checks=0,
            B4_calls=0, attempted_B4=0,
            attempted_new_arnoldi_directions=0,
            completed_new_arnoldi_directions=0,
            completed_legal_new_arnoldi_directions=0,
            legal_direction_count=0,
        )
        projection = np.zeros_like(rhs_array)
        projection_coefficients = np.zeros(pool_before, dtype=np.complex128)
        projection_matrix_bytes = 0
        projection_action: np.ndarray | None = None
        projection_post: float | None = None
        callback_solution: np.ndarray | None = None
        library_solution: np.ndarray | None = None
        library_info: Any = None
        abort: RecycledI4SafetyStop | RecycledI4WorkLimit | None = None
        validated_cu: list[tuple[np.ndarray, np.ndarray]] | None = None
        validated_facts: dict[str, Any] = {}
        pool_update = "unchanged"
        update_norm = 0.0
        update_evidence = False
        candidate_pairs: list[tuple[np.ndarray, np.ndarray]] = []
        # The local SciPy FGMRES loop calls one B4 immediately before the A4
        # matvec for that direction. Keep one state by call order; object ids
        # are not a numerical identity because LinearOperator may return a
        # reshaped view/copy. A direction is complete only after its A4 call
        # returns.
        pending_new: bool | None = None

        initial_memory = self._memory_facts(
            pool_before=pool_before, pool_before_bytes=pool_before_bytes, working=working,
            rhs=rhs_array, projection=projection, projection_matrix_bytes=0,
            inner_dimension=inner_dimension,
            pool_after_bytes=pool_before_bytes)
        if not initial_memory["cap_passed"]:
            raise RecycledI4Error("recycling live memory cap was exceeded")

        def invoke_action(value: np.ndarray) -> np.ndarray:
            nonlocal pending_new
            deadline.check("A4_before")
            counters["attempted_A4"] += 1
            counters["A4_matvec"] += 1
            pending = pending_new
            pending_new = None
            # The pending B4 result is a complete direction only if this A4
            # operation returns a finite vector below.
            output = _vector(self.action(value.copy()), name="A4 action", copy=False)
            if output.shape != value.shape:
                raise RecycledI4Error("A4 action returned the wrong shape")
            counters["completed_A4"] += 1
            if pending is not None:
                counters["completed_new_arnoldi_directions"] += 1
                if pending:
                    counters["completed_legal_new_arnoldi_directions"] += 1
                    counters["legal_direction_count"] += 1
            deadline.check("A4_after")
            return output

        def invoke_pc(value: np.ndarray) -> np.ndarray:
            nonlocal pending_new
            deadline.check("B4_before")
            if counters["attempted_B4"] >= MAX_NEW_B4:
                raise RecycledI4WorkLimit("new B4 application cap exceeded")
            if counters["attempted_new_arnoldi_directions"] >= MAX_NEW_DIRECTIONS:
                raise RecycledI4WorkLimit("new Arnoldi direction cap exceeded")
            counters["attempted_B4"] += 1
            counters["attempted_new_arnoldi_directions"] += 1
            output = _vector(self.pc(value.copy()), name="B4 action", copy=False)
            if output.shape != value.shape:
                raise RecycledI4Error("B4 action returned the wrong shape")
            counters["B4_calls"] += 1
            pending_new = _norm(output) > 0.0
            deadline.check("B4_after")
            return output

        def invoke_cached(value: np.ndarray) -> np.ndarray:
            deadline.check("cached_A4_before")
            counters["attempted_A4"] += 1
            counters["A4_matvec"] += 1
            counters["cached_A4_checks"] += 1
            output = _vector(self.action(value.copy()), name="cached A4 action", copy=False)
            if output.shape != value.shape:
                raise RecycledI4Error("cached A4 action returned the wrong shape")
            counters["completed_A4"] += 1
            deadline.check("cached_A4_after")
            return output

        def invoke_native(value: np.ndarray, *, enforce_deadline: bool = True,
                          check_after: bool = True) -> np.ndarray:
            if enforce_deadline:
                deadline.check("native_A4_before")
            counters["attempted_A4"] += 1
            counters["attempted_explicit_A4"] += 1
            counters["explicit_A4"] += 1
            counters["native_A4_checks"] += 1
            output = _vector(self.validation_action(value.copy()),
                             name="native A4 action", copy=False)
            if output.shape != value.shape:
                raise RecycledI4Error("native A4 action returned the wrong shape")
            counters["completed_A4"] += 1
            if check_after and enforce_deadline:
                deadline.check("native_A4_after")
            return output

        def callback(value: np.ndarray) -> None:
            nonlocal callback_solution
            callback_solution = _vector(value, name="gcrot callback solution", copy=True)
            _constraint_passes(self.u_constraint_check, callback_solution,
                               name="gcrot callback solution")
            deadline.check("gcrot callback")

        try:
            deadline.check("I4_start")
            if rhs_norm == 0.0:
                zero = np.zeros_like(rhs_array)
                memory = self._memory_facts(
                    pool_before=pool_before, pool_before_bytes=pool_before_bytes, working=working,
                    rhs=rhs_array, projection=projection, projection_matrix_bytes=0,
                    inner_dimension=inner_dimension,
                    pool_after_bytes=self.pool.retained_bytes)
                if not memory["cap_passed"]:
                    raise RecycledI4Error("recycling live memory cap was exceeded")
                facts = self._facts(
                    call_number=call_number, counters=counters,
                    pool_before=pool_before, pool_after=self.pool.size,
                    rhs_norm=0.0, absolute=0.0, relative=0.0,
                    elapsed=float(self.clock() - started),
                    status="INNER_ZERO_RHS", reason=0,
                    stop_reason="ZERO_RHS", requested_safe_return=False,
                    timeout_exceeded=False, library_info=0,
                    projection_pre=0.0, projection_post=0.0,
                    projection_coefficients=projection_coefficients,
                    projection_norm=0.0, pool_update="unchanged_zero_rhs",
                    pool_facts=dict(checked=False, pairs=pool_before, rank=pool_before),
                    memory=memory, legal_direction_count=0,
                    usable_new_directions=0)
                facts["input_unchanged"] = True
                return dict(solution=zero.copy(), applied=zero.copy(),
                            residual=zero.copy(), facts=facts)

            if pool_before:
                q_matrix = np.column_stack([q for _, q in pool_before_pairs])
                u_matrix = np.column_stack([u for u, _ in pool_before_pairs])
                projection_matrix_bytes = int(q_matrix.nbytes + u_matrix.nbytes)
                projection_memory = self._memory_facts(
                    pool_before=pool_before, pool_before_bytes=pool_before_bytes, working=working,
                    rhs=rhs_array, projection=projection,
                    projection_matrix_bytes=projection_matrix_bytes,
                    inner_dimension=inner_dimension,
                    pool_after_bytes=pool_before_bytes)
                if not projection_memory["cap_passed"]:
                    raise RecycledI4Error("recycling live memory cap was exceeded")
                projection_coefficients = q_matrix.conj().T @ rhs_array
                projection = _vector(u_matrix @ projection_coefficients,
                                     name="pool projection", copy=False)
                _constraint_passes(self.u_constraint_check, projection, name="pool projection")
                projection_action = invoke_native(projection)
                projection_post = _relative(
                    np.linalg.norm(rhs_array - projection_action), rhs_norm)
                del q_matrix, u_matrix
            else:
                projection_post = 1.0

            # ``pool_before_pairs`` only owns the same arrays referenced by
            # ``working``. Drop its list before SciPy's CU reorthogonalization
            # so the workspace has one owner at this point.
            del pool_before_pairs

            from scipy.sparse.linalg import LinearOperator, gcrotmk

            operator = LinearOperator((rhs_array.size, rhs_array.size), matvec=invoke_action,
                                      dtype=np.complex128)
            preconditioner = LinearOperator((rhs_array.size, rhs_array.size), matvec=invoke_pc,
                                            dtype=np.complex128)
            # The local implementation mutates CU in-place and appends a
            # (None, x.copy()) terminal snapshot. ``working`` is private and
            # is never handed to the persistent pool before final checks.
            library_solution, library_info = gcrotmk(
                operator, rhs_array.copy(), x0=None, tol=GCROT_TOL,
                maxiter=GCROT_MAXITER, M=preconditioner, callback=callback,
                m=GCROT_M, k=GCROT_K, CU=working, discard_C=False,
                truncate="smallest", atol=GCROT_ATOL)
            library_solution = _vector(library_solution, name="gcrot solution", copy=True)
            _constraint_passes(self.u_constraint_check, library_solution, name="gcrot solution")
        except RecycledI4SafetyStop as exc:
            abort = exc
        except RecycledI4WorkLimit as exc:
            abort = exc

        # An interrupted library call has no public partial least-squares
        # result. Return the last complete callback state, or the pool
        # projection; no partially transformed CU is eligible for commit.
        if library_solution is not None:
            candidate = library_solution.copy()
            candidate_source = "library"
        elif callback_solution is not None and np.isfinite(callback_solution).all():
            candidate = callback_solution.copy()
            candidate_source = "callback"
        else:
            candidate = projection.copy()
            candidate_source = "pool_projection" if pool_before else "zero_fallback"
        _constraint_passes(self.u_constraint_check, candidate, name="returned solution")

        if library_solution is not None:
            update_norm = _norm(library_solution - projection)
            # The pair-list length is an exact update witness until the pool is
            # full: SciPy appends one new CU pair after the single outer round.
            # At capacity, retain the exact zero-update diagnostic as the only
            # available library-level evidence; no absolute physical scale is
            # imposed on the RHS.
            candidate_pairs = self._candidate_pairs(working)
            update_evidence = bool(update_norm > 0.0)
            if pool_before < MAX_POOL_PAIRS:
                update_evidence = len(candidate_pairs) > pool_before

        if library_solution is not None:
            if (candidate_pairs and
                    counters["completed_legal_new_arnoldi_directions"] and
                    update_evidence):
                # The cadence is anchored to the absolute I4 call number:
                # first nonempty pool, then exactly calls 32, 64, ... .
                native_due = bool(
                    not self._native_spot_seen or
                    call_number % NATIVE_SPOT_INTERVAL == 0)
                def invoke_pool_native(value: np.ndarray) -> np.ndarray:
                    counters["pool_A4_checks"] += 1
                    return invoke_native(value, check_after=True)

                try:
                    validated_facts, validated_cu = self._validate_pool_candidate(
                        candidate_pairs,
                        inherited_closure_error=inherited_closure_error,
                        completed_new_directions=counters["completed_new_arnoldi_directions"],
                        call_number=call_number, invoke_cached=invoke_cached,
                        invoke_native=invoke_pool_native, native_spot_due=native_due)
                    pool_update = "validated_pending_final_commit"
                except RecycledI4SafetyStop as exc:
                    abort = abort or exc
                    validated_facts = {}
                    validated_cu = None
                    pool_update = "rejected_safety_deadline"

        # The final native action is authoritative. Once a safety stop has
        # happened, allow this one finite residual evaluation to complete; its
        # actual elapsed time is classified below.
        try:
            if projection_action is not None and np.array_equal(candidate, projection):
                final_action = projection_action.copy()
            else:
                final_action = invoke_native(
                    candidate, enforce_deadline=abort is None, check_after=False)
        except RecycledI4SafetyStop as exc:
            abort = abort or exc
            final_action = invoke_native(candidate, enforce_deadline=False, check_after=False)
        final_action = _vector(final_action, name="returned native action", copy=True)
        if final_action.shape != candidate.shape or not np.isfinite(final_action).all():
            raise RecycledI4Error("returned native action is invalid")
        residual = rhs_array - final_action
        if not np.isfinite(residual).all():
            raise RecycledI4Error("returned true residual is invalid")
        absolute = _norm(residual)
        relative = _relative(absolute, rhs_norm)
        _constraint_passes(self.q_constraint_check, final_action, name="returned native action")
        _constraint_passes(self.q_constraint_check, residual, name="returned residual")

        elapsed = float(self.clock() - started)
        if not np.isfinite(elapsed):
            raise RecycledI4Error("non-finite final elapsed time")
        # Do not infer final timeout state solely from the first callback
        # exception. Native validation may consume the remaining budget.
        actual_hard = elapsed >= self.hard_seconds
        actual_safe = elapsed >= self.safe_seconds
        if actual_hard:
            status = "INNER_APPROXIMATE_RETURN"
            stop_reason = "I4_HARD_TIME_EXCEEDED"
            requested_safe_return = True
            timeout_exceeded = True
        elif actual_safe:
            status = "INNER_APPROXIMATE_RETURN"
            stop_reason = (abort.reason if isinstance(abort, RecycledI4SafetyStop)
                           and abort.reason == "OUTER_SAFE_DEADLINE"
                           else "I4_SAFE_RETURN_REQUESTED")
            requested_safe_return = True
            timeout_exceeded = False
        elif abort is not None:
            status = "INNER_APPROXIMATE_RETURN"
            stop_reason = abort.reason
            requested_safe_return = isinstance(abort, RecycledI4SafetyStop)
            timeout_exceeded = False
        else:
            status = "INNER_TARGET_REACHED" if relative <= self.target else "INNER_APPROXIMATE_RETURN"
            stop_reason = "TARGET_REACHED" if relative <= self.target else "MAXITER_ONE"
            requested_safe_return = False
            timeout_exceeded = False

        input_unchanged = bool(np.array_equal(original, rhs_array))
        if not input_unchanged:
            raise RecycledI4Error("rhs was changed by recycled I4")
        memory = self._memory_facts(
            pool_before=pool_before, pool_before_bytes=pool_before_bytes, working=working,
            rhs=rhs_array, projection=projection,
            projection_matrix_bytes=projection_matrix_bytes,
            inner_dimension=inner_dimension,
            pool_after_bytes=self.pool.retained_bytes)
        if not memory["cap_passed"]:
            raise RecycledI4Error("recycling live memory cap was exceeded")

        # Pool mutation is last. Native residual, finite checks, input identity,
        # memory and deadline classification all precede this assignment. A
        # soft/hard return or a work abort never commits.
        if (validated_cu is not None and library_solution is not None and abort is None
                and elapsed < self.safe_seconds):
            self.pool._commit_owned(validated_cu, validated_facts["closure_errors"])
            if validated_facts.get("native_spot_checked", 0):
                self._native_spot_seen = True
                self._last_native_spot_call = call_number
            pool_update = "committed"
        elif validated_cu is not None:
            pool_update = "validated_not_committed_deadline"
        # The peak bound was computed before the transaction, while the
        # retained field must describe the actual post-transaction pool.
        memory["retained_bytes"] = int(self.pool.retained_bytes)

        # A nonzero pool projection is a usable return even when this RHS made
        # no new direction. An interrupted new direction is not usable unless
        # the complete library result was returned.
        pool_projection_legal = int(_norm(projection) > 0.0)
        usable_new = (counters["completed_legal_new_arnoldi_directions"]
                      if library_solution is not None and update_evidence else 0)
        legal_direction_count = pool_projection_legal + int(usable_new)
        counters["legal_direction_count"] = legal_direction_count
        pool_facts = (dict(validated_facts, checked=True)
                      if validated_facts else
                      dict(checked=False, pairs=pool_before, rank=pool_before))
        facts = self._facts(
            call_number=call_number, counters=counters,
            pool_before=pool_before, pool_after=self.pool.size,
            rhs_norm=rhs_norm, absolute=absolute, relative=relative,
            elapsed=elapsed, status=status,
            reason=(library_info if library_info is not None else stop_reason),
            stop_reason=stop_reason,
            requested_safe_return=requested_safe_return,
            timeout_exceeded=timeout_exceeded, library_info=library_info,
            projection_pre=1.0, projection_post=projection_post,
            projection_coefficients=projection_coefficients,
            projection_norm=_norm(projection), pool_update=pool_update,
            pool_facts=pool_facts, memory=memory,
            legal_direction_count=legal_direction_count,
            usable_new_directions=usable_new)
        facts["candidate_source"] = candidate_source
        facts["new_update_norm"] = float(update_norm)
        facts["new_update_evidence"] = update_evidence
        facts["input_unchanged"] = input_unchanged
        return dict(solution=candidate, applied=final_action, residual=residual, facts=facts)


__all__ = [
    "BoundedGCROTI4",
    "CLOSURE_LIMIT",
    "GCROT_ATOL",
    "GCROT_K",
    "GCROT_M",
    "GCROT_MAXITER",
    "GCROT_TOL",
    "MAX_NEW_B4",
    "MAX_NEW_DIRECTIONS",
    "MAX_POOL_PAIRS",
    "NATIVE_SPOT_INTERVAL",
    "ORTHOGONALITY_LIMIT",
    "POOL_NUMERIC_BYTES_P4_DERIVED",
    "RANK_THRESHOLD",
    "RECYCLING_EXTRA_BYTES_LIMIT",
    "RecycledI4Error",
    "RecycledI4SafetyStop",
    "RecycledI4WorkLimit",
    "VerifiedRecyclingPool",
    "gcrotmk_backend_facts",
]
