"""Fixed-cell local spectral data for the N1 auxiliary hierarchy.

The local generalized problem is built on a constrained cell-supported block,
not on an interface trace:

    B0 = (mu_r**-1 curl u, curl v) + k0**2 (|epsilon_r| u, v),
    B0 q = lambda M_local q.

``M_local`` is the volumetric mass metric corresponding to the second term in
``B0``.  Canonical row keys and inverse multiplicities are supplied by the
caller.  They are used for deterministic phase anchors and shared-entity
partition-of-unity contributions; no trace mass, residual, source, or rho is
accepted here.  A class factor is stored only on its deterministic MPI owner;
bounded RHS/solution routing is the only cross-rank factor access.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from types import MappingProxyType
from typing import Any

import numpy as np
from mpi4py import MPI


N1_PROFILE = "bounded_local_spectral_multilevel_v1"
N1_MAX_LOCAL_ROWS = 882
N1_MAX_CLASSES = 32
N1_FACTOR_BYTES_LIMIT = 6_230_448
N1_MODE_CAP = 8
N1_GRADIENT_COUNT = 3
N1_POSITIVE_MODE_COUNT = 5
N1_REGIONAL_RANK = 16
N1_TOP_RANK = 32
N1_LEVELS = 2
N1_SHARED_WEIGHT = "inverse_global_multiplicity"
N1_ALGEBRA_LIMIT = 1.0e-11
N1_PO_U_LIMIT = 1.0e-13
N1_RP_LIMIT = 1.0e-13
N1_REPEAT_LIMIT = 1.0e-13
N1_DEPENDENCY_TOL = 1.0e-14
N1_PHASE_ZERO = 64.0 * np.finfo(np.float64).eps
N1_DEGENERATE_CLUSTER_ULPS = 256.0


def _relative(value: np.ndarray, reference: np.ndarray) -> float:
    numerator = float(np.linalg.norm(np.asarray(value)))
    denominator = max(float(np.linalg.norm(np.asarray(reference))), 1.0e-300)
    return numerator / denominator


def _hermitian_defect(matrix: np.ndarray) -> float:
    array = np.asarray(matrix, dtype=np.complex128)
    return _relative(array - array.conj().T, array)


def _class_digest(value: str) -> str:
    digest = str(value).lower()
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    return digest


def deterministic_class_owner(class_digest: str, mpi_size: int) -> int:
    """Return the fixed global owner for one exact class digest."""

    size = int(mpi_size)
    if size < 1:
        raise ValueError("mpi_size must be positive")
    digest = bytes.fromhex(_class_digest(class_digest))
    return int.from_bytes(digest[:8], "big") % size


def packed_lower_bytes(rows: int) -> int:
    """Return exact complex128 bytes for one lower-packed factor."""

    size = int(rows)
    if size < 1:
        raise ValueError("factor rows must be positive")
    return size * (size + 1) // 2 * np.dtype(np.complex128).itemsize


def canonical_vector_digest(keys: Iterable[Any], values: np.ndarray) -> str:
    """Hash ordered canonical keys and one owner-local complex vector."""

    ordered_keys = tuple(keys)
    array = np.ascontiguousarray(np.asarray(values, dtype=np.complex128))
    if array.ndim != 1 or array.size != len(ordered_keys):
        raise ValueError("canonical keys and values do not have matching shapes")
    payload = {
        "keys": ordered_keys,
        "values": [[float(value.real), float(value.imag)] for value in array],
    }
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def canonical_pou_closure_error(
    contributions: Iterable[tuple[Iterable[Any], np.ndarray]],
    expected: Mapping[Any, complex],
) -> float:
    """Compare summed canonical PoU contributions with a physical vector.

    This is a small-oracle helper.  Production callers can reduce the same
    keyed contributions by owner without collecting FE-sized numeric arrays.
    """

    totals: dict[Any, complex] = {}
    for keys, values in contributions:
        ordered_keys = tuple(keys)
        array = np.asarray(values, dtype=np.complex128)
        if array.ndim != 1 or len(ordered_keys) != array.size:
            raise ValueError("PoU contribution keys and values do not match")
        for key, value in zip(ordered_keys, array, strict=True):
            totals[key] = totals.get(key, 0.0j) + complex(value)
    if set(totals) != set(expected):
        raise ValueError("PoU contributions do not close the expected key set")
    actual = np.asarray([totals[key] for key in expected], dtype=np.complex128)
    reference = np.asarray([expected[key] for key in expected], dtype=np.complex128)
    return _relative(actual - reference, reference)


def build_regional_rayleigh_ritz(
    region_candidates: Mapping[Any, np.ndarray],
    region_stiffness: Mapping[Any, np.ndarray],
    region_mass: Mapping[Any, np.ndarray],
    region_candidate_keys: Mapping[Any, Sequence[Any]] | None = None,
) -> Mapping[Any, Mapping[str, Any]]:
    """Solve one small candidate-space Ritz problem per supplied region.

    ``region_candidates`` is the canonical row-by-candidate matrix ``C``;
    callers must keep at most 64 columns.  ``region_stiffness`` and
    ``region_mass`` are the streamed candidate-space matrices
    ``B_c=C^H B C`` and ``M_c=C^H M C``.  No row-by-row regional operator is
    accepted or materialized.
    """

    if set(region_candidates) != set(region_stiffness) or set(
        region_candidates
    ) != set(region_mass):
        raise ValueError("regional C, Bc, and Mc maps must agree")
    results: dict[Any, Mapping[str, Any]] = {}
    for region in sorted(region_candidates, key=repr):
        candidates = np.asarray(region_candidates[region], dtype=np.complex128)
        stiffness = np.asarray(region_stiffness[region], dtype=np.complex128)
        mass = np.asarray(region_mass[region], dtype=np.complex128)
        if candidates.ndim != 2 or candidates.shape[1] > 64:
            raise ValueError("regional C must have at most 64 candidate columns")
        candidate_count = int(candidates.shape[1])
        if stiffness.shape != (candidate_count, candidate_count):
            raise ValueError("regional Bc shape does not match C")
        if mass.shape != stiffness.shape:
            raise ValueError("regional Mc shape does not match Bc")
        if not np.all(np.isfinite(candidates)) or not np.all(
            np.isfinite(stiffness)
        ) or not np.all(np.isfinite(mass)):
            raise ValueError("regional C/Bc/Mc inputs must be finite")
        mass = (mass + mass.conj().T) * 0.5
        mass_factor = np.linalg.cholesky(mass)
        normalization = np.linalg.solve(
            mass_factor.conj().T,
            np.eye(candidate_count, dtype=np.complex128),
        )
        mass_values = np.linalg.eigvalsh(mass)
        mass_minimum = float(np.min(mass_values))
        mass_condition = float(np.max(mass_values) / mass_minimum)
        projected = normalization.conj().T @ stiffness @ normalization
        projected = (projected + projected.conj().T) * 0.5
        eigenvalues, eigenvectors = np.linalg.eigh(projected)
        selected = min(N1_REGIONAL_RANK, int(eigenvalues.size))
        if region_candidate_keys is None:
            candidate_keys = tuple(("candidate", index) for index in range(candidate_count))
        else:
            candidate_keys = tuple(region_candidate_keys[region])
        if len(candidate_keys) != candidate_count or len(set(candidate_keys)) != candidate_count:
            raise ValueError("regional canonical candidate keys do not match C")
        coefficients, selected_values, cluster_sizes = (
            canonicalize_degenerate_eigenvectors(
                eigenvalues,
                normalization @ eigenvectors,
                mass,
                stiffness,
                candidate_keys,
                tuple(range(selected)),
            )
        )
        mass_defect = _relative(
            coefficients.conj().T @ mass @ coefficients
            - np.eye(selected),
            np.eye(selected),
        )
        residuals = []
        for column, value in enumerate(coefficients.T):
            residual = stiffness @ value - selected_values[column] * (mass @ value)
            denominator = max(
                float(np.linalg.norm(stiffness @ value)),
                float(np.linalg.norm(selected_values[column] * (mass @ value))),
                np.finfo(float).tiny,
            )
            residuals.append(float(np.linalg.norm(residual) / denominator))
        if mass_defect > N1_ALGEBRA_LIMIT:
            raise RuntimeError(
                f"regional M orthogonality {mass_defect} exceeds limit "
                f"{N1_ALGEBRA_LIMIT}"
            )
        coefficients.flags.writeable = False
        results[region] = MappingProxyType(
            {
                "coefficients": coefficients,
                "eigenvalues": selected_values,
                "candidate_count": candidate_count,
                "candidate_m_rank": candidate_count,
                "selected_rank": int(selected),
                "mass_orthogonality": float(mass_defect),
                "projected_eigen_residual": float(max(residuals, default=0.0)),
                "projected_dimension": int(projected.shape[0]),
                "selected_spectral_cluster_sizes": cluster_sizes,
                "mass_min_eigenvalue": mass_minimum,
                "mass_condition_estimate": mass_condition,
                "source_independent": True,
                "rank_cap": N1_REGIONAL_RANK,
                "regional_dense_row_operator_materialized": False,
            }
        )
    return MappingProxyType(results)


class ExactClassOwnerPlan:
    """Own one packed factor per exact class and route bounded solves."""

    def __init__(self, class_digests: Iterable[str], comm: Any = MPI.COMM_WORLD):
        self.comm = comm
        unique = tuple(sorted({_class_digest(value) for value in class_digests}))
        if not unique:
            raise ValueError("at least one exact class is required")
        if len(unique) > N1_MAX_CLASSES:
            raise RuntimeError(
                f"exact class count {len(unique)} exceeds limit {N1_MAX_CLASSES}"
            )
        self.class_digests = unique
        self.owners = MappingProxyType(
            {
                digest: deterministic_class_owner(digest, comm.size)
                for digest in unique
            }
        )
        self._factors: dict[str, tuple[_PackedCholesky, str]] = {}
        self._factor_audits: dict[str, dict[str, Any]] = {}

    def owner(self, class_digest: str) -> int:
        return int(self.owners[_class_digest(class_digest)])

    @property
    def factor_count(self) -> int:
        return len(self._factors)

    @property
    def factor_bytes(self) -> int:
        return sum(factor.nbytes for factor, _digest in self._factors.values())

    def ensure_factor(
        self, class_digest: str, matrix: np.ndarray
    ) -> tuple[_PackedCholesky | None, bool]:
        """Create or reuse the one factor assigned to one exact class."""

        digest = _class_digest(class_digest)
        if self.owner(digest) != self.comm.rank:
            return None, False
        array = np.ascontiguousarray(np.asarray(matrix, dtype=np.complex128))
        operator_digest = hashlib.sha256(array.view(np.uint8)).hexdigest()
        existing = self._factors.get(digest)
        if existing is not None:
            factor, stored_digest = existing
            if stored_digest != operator_digest:
                raise RuntimeError(
                    f"exact class {digest} has incompatible local B0 operator digest"
                )
            return factor, True
        factor = _PackedCholesky(array)
        if factor.nbytes > N1_FACTOR_BYTES_LIMIT:
            raise RuntimeError(
                f"packed factor bytes {factor.nbytes} exceed limit "
                f"{N1_FACTOR_BYTES_LIMIT}"
            )
        fixed_rhs = np.arange(array.shape[0], dtype=np.float64) + (0.125 + 0.25j)
        fixed_solution = factor.solve(fixed_rhs)
        fixed_residual = _relative(array @ fixed_solution - fixed_rhs, fixed_rhs)
        if not np.isfinite(fixed_residual) or fixed_residual > N1_ALGEBRA_LIMIT:
            raise RuntimeError(
                f"fixed local factor solve residual {fixed_residual:.17g} "
                f"exceeds limit {N1_ALGEBRA_LIMIT:.17g}"
            )
        self._factor_audits[digest] = {
            "factorization_relative_error": float(
                factor.factorization_relative_error
            ),
            "fixed_rhs_solve_residual": float(fixed_residual),
            "factor_bytes": int(factor.nbytes),
            "factor_owner_rank": int(self.comm.rank),
            "factor_audit_measured_once_per_class": True,
        }
        self._factors[digest] = (factor, operator_digest)
        return factor, False

    def factor_audit(self, class_digest: str) -> Mapping[str, Any] | None:
        """Return the owner-measured scalar audit for one retained factor."""

        value = self._factor_audits.get(_class_digest(class_digest))
        return None if value is None else MappingProxyType(dict(value))

    @property
    def local_factor_audits(self) -> Mapping[str, Mapping[str, Any]]:
        return MappingProxyType(
            {
                digest: MappingProxyType(dict(value))
                for digest, value in self._factor_audits.items()
            }
        )

    def register_class_representative(
        self,
        class_digest: str,
        matrix: np.ndarray | None,
        *,
        slot: int,
    ) -> None:
        """Send one bounded class representative to its fixed hash owner.

        All ranks enter every global class slot.  Only the lowest active rank
        sends one dense local block to the deterministic owner; the owner
        keeps the packed factor and all other ranks release the block after
        this call.  The payload is one local class matrix, never a FE-sized
        numeric collective.
        """

        digest = _class_digest(class_digest)
        if slot < 0 or slot >= len(self.class_digests) or self.class_digests[slot] != digest:
            raise ValueError("class representative slot is not the global class slot")
        if matrix is not None:
            candidate_matrix = np.ascontiguousarray(
                np.asarray(matrix, dtype=np.complex128)
            )
            if (
                candidate_matrix.ndim != 2
                or candidate_matrix.shape[0] != candidate_matrix.shape[1]
                or candidate_matrix.shape[0] > N1_MAX_LOCAL_ROWS
            ):
                raise ValueError("class representative matrix exceeds local row cap")
        else:
            candidate_matrix = None
        candidate_rank = self.comm.allreduce(
            self.comm.rank if candidate_matrix is not None else self.comm.size,
            op=MPI.MIN,
        )
        if candidate_rank == self.comm.size:
            raise RuntimeError(f"no representative supplied for exact class {digest}")
        owner = self.owner(digest)
        error = None
        try:
            if self.comm.rank == owner:
                if owner == candidate_rank:
                    received = candidate_matrix
                else:
                    received = self.comm.recv(
                        source=int(candidate_rank),
                        tag=1000 + int(slot),
                    )
                self.ensure_factor(digest, received)
            elif self.comm.rank == candidate_rank:
                self.comm.send(
                    candidate_matrix,
                    dest=owner,
                    tag=1000 + int(slot),
                )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        errors = self.comm.gather(error, root=0)
        if self.comm.rank == 0:
            first_error = next((value for value in errors if value is not None), None)
        else:
            first_error = None
        first_error = self.comm.bcast(first_error, root=0)
        if first_error is not None:
            raise RuntimeError(f"class representative registration failed: {first_error}")

    def register_class_template(
        self,
        class_digest: str,
        template_row_keys: Sequence[Any] | None,
        template_modes: np.ndarray | None,
        *,
        slot: int,
        representative_rank: int,
        participant_ranks: Sequence[int],
    ) -> tuple[tuple[Any, ...], np.ndarray] | None:
        """Route one bounded eight-mode class template to its patch ranks.

        The representative is the only rank that constructs the template.
        It sends at most ``882 * 8`` complex entries to the deterministic
        factor owner; that owner forwards the same bounded payload only to
        ranks that own a patch of this class.  No rank-wide numeric collective
        or full-space basis replication is used.  The owner may discard the
        template immediately when it has no local patch.
        """

        digest = _class_digest(class_digest)
        if slot < 0 or slot >= len(self.class_digests) or self.class_digests[slot] != digest:
            raise ValueError("class template slot is not the global class slot")
        participants = tuple(sorted({int(rank) for rank in participant_ranks}))
        if not participants or any(rank < 0 or rank >= self.comm.size for rank in participants):
            raise ValueError("class template participants must be valid non-empty ranks")
        if int(representative_rank) not in participants:
            raise ValueError("class template representative must own this class")
        is_representative = self.comm.rank == int(representative_rank)
        if is_representative:
            if template_row_keys is None or template_modes is None:
                raise ValueError("representative must provide class template data")
            keys = tuple(template_row_keys)
            modes = np.ascontiguousarray(np.asarray(template_modes, dtype=np.complex128))
            if (
                not keys
                or len(keys) > N1_MAX_LOCAL_ROWS
                or len(set(keys)) != len(keys)
                or modes.shape != (len(keys), N1_MODE_CAP)
                or not np.all(np.isfinite(modes))
            ):
                raise ValueError("class template shape or values exceed bounded contract")
            payload = (keys, modes)
        else:
            payload = None

        owner = self.owner(digest)
        if self.comm.rank == owner:
            if owner == int(representative_rank):
                received = payload
            else:
                received = self.comm.recv(source=int(representative_rank), tag=2000 + int(slot))
            if received is None:
                raise RuntimeError("class template owner received no representative payload")
            owner_keys, owner_modes = received
            for rank in participants:
                if rank != owner:
                    self.comm.send((owner_keys, owner_modes), dest=rank, tag=3000 + int(slot))
            if owner in participants:
                result = (tuple(owner_keys), np.ascontiguousarray(owner_modes))
            else:
                result = None
        elif is_representative:
            self.comm.send(payload, dest=owner, tag=2000 + int(slot))
            result = (
                tuple(payload[0]),
                np.ascontiguousarray(payload[1]),
            ) if owner == int(representative_rank) else self.comm.recv(
                source=owner, tag=3000 + int(slot)
            )
        elif self.comm.rank in participants:
            result = self.comm.recv(source=owner, tag=3000 + int(slot))
        else:
            result = None

        if result is None:
            return None
        result_keys, result_modes = result
        return tuple(result_keys), np.ascontiguousarray(result_modes, dtype=np.complex128)

    def owner_solve(self, class_digest: str, right_hand_side: np.ndarray) -> np.ndarray:
        """Solve on the unique class owner using its packed factor."""

        digest = _class_digest(class_digest)
        entry = self._factors.get(digest)
        if entry is None or self.owner(digest) != self.comm.rank:
            raise RuntimeError("owner factor is unavailable for this class")
        return entry[0].solve(right_hand_side)

    def destroy(self) -> None:
        """Release this shared class-factor store exactly once."""

        self._factors.clear()
        self._factor_audits.clear()

    @property
    def audit(self) -> Mapping[str, Any]:
        local_owned = sum(owner == self.comm.rank for owner in self.owners.values())
        return MappingProxyType(
            {
                "schema": "fullspace.local-spectral-class-owner.v1",
                "rule": "hash(exact_class_digest) mod mpi_size",
                "global_class_count": len(self.class_digests),
                "owners": dict(self.owners),
                "local_factor_class_count": int(local_owned),
                "local_factor_count_measured": self.factor_count,
                "local_factor_bytes_measured": self.factor_bytes,
                "local_factor_audits": {
                    digest: dict(value)
                    for digest, value in self._factor_audits.items()
                },
                "one_global_factor_per_class": True,
                "per_rank_factor_replication": False,
                "bounded_owner_route_entries": N1_MAX_LOCAL_ROWS,
                "route": "bounded_owner_rhs_gather_solution_scatter",
                "class_factor_registration": (
                    "fixed_global_class_slots_lowest_representative_to_hash_owner"
                ),
                "numeric_allgather": False,
                "mpi_identity_measured_by_caller": True,
            }
        )

    def route_solve(
        self,
        class_digest: str,
        right_hand_side: np.ndarray,
        *,
        request_id: int,
        active: bool = True,
    ) -> np.ndarray:
        """Route one bounded RHS through a fixed tagged owner schedule.

        Every rank participates in the same request id and class slot.  An
        inactive rank sends zeros, so later patch/class slots cannot silently
        shift the collective sequence.  Only metadata is gathered for schedule
        validation; numeric payloads are one local block per rank.
        """

        digest = _class_digest(class_digest)
        rhs = np.ascontiguousarray(np.asarray(right_hand_side, dtype=np.complex128))
        request = int(request_id)
        if request < 0:
            raise ValueError("owner-route request_id must be non-negative")
        if rhs.ndim != 1 or rhs.size > N1_MAX_LOCAL_ROWS:
            raise ValueError("owner-route payload exceeds the local row cap")
        active_flag = bool(active)
        owner = self.owner(digest)
        metadata = {
            "request_id": request,
            "class_digest": digest,
            "active": active_flag,
            "payload_entries": int(rhs.size),
        }
        metadata_rows = self.comm.gather(metadata, root=owner)
        if self.comm.rank == owner:
            schedule_error = None
            for row in metadata_rows:
                if row["request_id"] != request or row["class_digest"] != digest:
                    schedule_error = "owner-route metadata request/class mismatch"
                    break
                if row["payload_entries"] != rhs.size:
                    schedule_error = "owner-route metadata payload-size mismatch"
                    break
        else:
            schedule_error = None
        schedule_error = self.comm.bcast(schedule_error, root=owner)
        if schedule_error is not None:
            raise RuntimeError(schedule_error)

        requests = self.comm.gather((active_flag, rhs), root=owner)
        if self.comm.rank == owner:
            solutions = []
            route_error = None
            try:
                for request_active, request_values in requests:
                    if request_active:
                        solution = self.owner_solve(digest, request_values)
                    else:
                        solution = np.zeros_like(request_values)
                    solutions.append(
                        np.ascontiguousarray(solution, dtype=np.complex128)
                    )
            except Exception as exc:
                route_error = f"owner-route solve failed: {type(exc).__name__}: {exc}"
        else:
            solutions = None
            route_error = None
        route_error = self.comm.bcast(route_error, root=owner)
        if route_error is not None:
            raise RuntimeError(route_error)
        result = self.comm.scatter(solutions, root=owner)
        return np.ascontiguousarray(np.asarray(result, dtype=np.complex128))


N2_TOP_MIXING_SCHEMA = "task038.n2.top-mixing.sha256.v1"
N2_TOP_MIXING_SEED = "task038-extra-fixed-top-seed-20260822"


def deterministic_row_owner(row_key: Any, mpi_size: int) -> int:
    """Choose an owner from a canonical row key, never from a PETSc id."""

    size = int(mpi_size)
    if size < 1:
        raise ValueError("mpi_size must be positive")
    frame = repr(("task038.n2.row-owner.v1", row_key)).encode("utf-8")
    digest = hashlib.sha256(frame).digest()
    return int.from_bytes(digest[:8], "big") % size


def top_mixing_coefficient(
    region_key: Any, regional_mode_index: int, top_index: int
) -> complex:
    """Return one fixed source-independent SHA256 mixing coefficient."""

    frame = repr(
        (
            N2_TOP_MIXING_SCHEMA,
            N2_TOP_MIXING_SEED,
            region_key,
            int(regional_mode_index),
            int(top_index),
        )
    ).encode("utf-8")
    digest = hashlib.sha256(frame).digest()
    real = int.from_bytes(digest[:8], "big") / 2.0**64 - 0.5
    imag = int.from_bytes(digest[8:16], "big") / 2.0**64 - 0.5
    return complex(real, imag)


def _owner_local_byte_stats(comm: Any, local_bytes: int) -> dict[str, int]:
    value = int(local_bytes)
    return {
        "local": value,
        "global_sum": int(comm.allreduce(value, op=MPI.SUM)),
        "global_max": int(comm.allreduce(value, op=MPI.MAX)),
    }


class OwnerLocalMultilevelBasis:
    """Retain regional Z16 and mixed/orthonormal top Z32 by row owner."""

    def __init__(
        self,
        row_keys: Sequence[Any],
        regional_columns: np.ndarray,
        top_columns: np.ndarray,
        *,
        regional_mode_count: int,
        comm: Any,
        top_orthogonality_defect: float,
        physical_row_keys: Sequence[Any] | None = None,
        active_row_positions: Sequence[int] | None = None,
        row_order_audit: str = "canonical_owner_local_order",
    ) -> None:
        keys = tuple(row_keys)
        physical_keys = keys if physical_row_keys is None else tuple(physical_row_keys)
        positions = (
            np.arange(len(keys), dtype=np.int64)
            if active_row_positions is None
            else np.asarray(active_row_positions, dtype=np.int64)
        )
        regional = np.ascontiguousarray(
            np.asarray(regional_columns, dtype=np.complex128)
        )
        top = np.ascontiguousarray(np.asarray(top_columns, dtype=np.complex128))
        if len(set(keys)) != len(keys):
            raise ValueError("owner-local multilevel row keys are duplicated")
        if positions.ndim != 1 or positions.size != len(keys):
            raise ValueError("active physical row positions do not match keys")
        if np.unique(positions).size != positions.size or np.any(positions < 0):
            raise ValueError("active physical row positions are not unique")
        if any(int(position) >= len(physical_keys) for position in positions):
            raise ValueError("active physical row position is outside owned rows")
        if tuple(physical_keys[int(position)] for position in positions) != keys:
            raise ValueError("physical row order does not preserve canonical active keys")
        if regional.ndim != 2 or regional.shape[0] != len(physical_keys):
            raise ValueError("regional Z16 rows do not match physical owned rows")
        if regional.shape[1] != N1_REGIONAL_RANK:
            raise ValueError("regional owner-local basis must have rank 16")
        if top.shape != (len(physical_keys), N1_TOP_RANK):
            raise ValueError("top owner-local basis must have rank 32")
        if not np.all(np.isfinite(regional)) or not np.all(np.isfinite(top)):
            raise ValueError("multilevel basis values must be finite")
        regional.flags.writeable = False
        top.flags.writeable = False
        self.comm = comm
        self._row_keys = keys
        self._physical_row_keys = physical_keys
        self._active_row_positions = np.ascontiguousarray(positions, dtype=np.int64)
        self._active_row_positions.flags.writeable = False
        position_digest = hashlib.sha256(
            self._active_row_positions.tobytes(order="C")
        ).hexdigest()
        self._regional_columns = regional
        self._columns = top
        self._audit = MappingProxyType(
            {
                "schema": "fullspace.n2.owner-local-multilevel-basis.v1",
                "regional_rank": N1_REGIONAL_RANK,
                "top_rank": N1_TOP_RANK,
                "regional_mode_count": int(regional_mode_count),
                "regional_z16_bytes": _owner_local_byte_stats(
                    comm, regional.nbytes
                ),
                "top_z32_bytes": _owner_local_byte_stats(comm, top.nbytes),
                "top_orthogonality_relative_defect": float(
                    top_orthogonality_defect
                ),
                "top_mixing_schema": N2_TOP_MIXING_SCHEMA,
                "top_mixing_seed": N2_TOP_MIXING_SEED,
                "top_gram_collective": "32x32_small_numeric_allreduce",
                "regional_columns_semantics": (
                    "fixed_global_sum_of_same_regional_mode_index_rank16"
                ),
                "top_columns_semantics": (
                    "region_distinguished_fixed_sha256_mix_rank32"
                ),
                "row_order": str(row_order_audit),
                "physical_owned_rows": len(physical_keys),
                "active_owned_rows": len(keys),
                "owned_slave_rows": len(physical_keys) - len(keys),
                "active_row_position_count": int(positions.size),
                "active_row_positions_sha256": position_digest,
                "canonical_key_scatter": (
                    "hash_owner_staging_to_dofmap_owned_local_order"
                    if row_order_audit == "physical_dofmap_owned_local_order"
                    else "not_required"
                ),
                "canonical_identity_excludes_owned_slave_rows": True,
                "construction_workspace_released": True,
                "regional_shards_owner_local": True,
                "global_numeric_allgather": False,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "global_factor_materialized": False,
                "global_direct_coarse_solve": False,
            }
        )
        self._destroyed = False

    @property
    def columns(self) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("multilevel basis has been destroyed")
        view = self._columns.view()
        view.flags.writeable = False
        return view

    @property
    def regional_columns(self) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("multilevel basis has been destroyed")
        view = self._regional_columns.view()
        view.flags.writeable = False
        return view

    @property
    def row_keys(self) -> tuple[Any, ...]:
        return self._row_keys

    @property
    def physical_row_keys(self) -> tuple[Any, ...]:
        return self._physical_row_keys

    @property
    def active_row_positions(self) -> np.ndarray:
        view = self._active_row_positions.view()
        view.flags.writeable = False
        return view

    @property
    def audit(self) -> Mapping[str, Any]:
        return self._audit

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._columns = np.empty((0, N1_TOP_RANK), dtype=np.complex128)
        self._regional_columns = np.empty(
            (0, N1_REGIONAL_RANK), dtype=np.complex128
        )


def build_owner_local_multilevel_basis(
    row_keys: Sequence[Any],
    regional_columns: np.ndarray,
    top_raw_columns: np.ndarray,
    *,
    regional_mode_count: int,
    comm: Any = MPI.COMM_WORLD,
    physical_row_keys: Sequence[Any] | None = None,
    active_row_positions: Sequence[int] | None = None,
    row_order_audit: str = "canonical_owner_local_order",
) -> OwnerLocalMultilevelBasis:
    """Normalize one owner-local regional/top construction without FE gather."""

    keys = tuple(row_keys)
    regional = np.ascontiguousarray(
        np.asarray(regional_columns, dtype=np.complex128)
    )
    raw_top = np.ascontiguousarray(np.asarray(top_raw_columns, dtype=np.complex128))
    physical_keys = keys if physical_row_keys is None else tuple(physical_row_keys)
    expected_rows = len(physical_keys)
    if regional.shape != (expected_rows, N1_REGIONAL_RANK):
        raise ValueError("regional Z16 shape is not physical-owner-local and fixed")
    if raw_top.shape != (expected_rows, N1_TOP_RANK):
        raise ValueError("top raw shape is not owner-local and fixed")
    if int(regional_mode_count) < N1_TOP_RANK:
        raise RuntimeError(
            f"top rank {N1_TOP_RANK} requires at least {N1_TOP_RANK} "
            f"regional modes; value={int(regional_mode_count)}"
        )
    gram = np.asarray(
        comm.allreduce(raw_top.conj().T @ raw_top, op=MPI.SUM),
        dtype=np.complex128,
    )
    if not np.all(np.isfinite(gram)):
        raise RuntimeError("top Gram is non-finite")
    factor = np.linalg.cholesky((gram + gram.conj().T) * 0.5)
    normalization = np.linalg.solve(
        factor.conj().T, np.eye(N1_TOP_RANK, dtype=np.complex128)
    )
    top = np.ascontiguousarray(raw_top @ normalization)
    top_gram = np.asarray(
        comm.allreduce(top.conj().T @ top, op=MPI.SUM),
        dtype=np.complex128,
    )
    defect = _relative(
        top_gram - np.eye(N1_TOP_RANK, dtype=np.complex128),
        np.eye(N1_TOP_RANK, dtype=np.complex128),
    )
    if not np.isfinite(defect) or defect > N1_ALGEBRA_LIMIT:
        raise RuntimeError(
            f"top Z32 orthogonality {defect:.17g} exceeds limit "
            f"{N1_ALGEBRA_LIMIT:.17g}"
        )
    basis = OwnerLocalMultilevelBasis(
        keys,
        regional,
        top,
        regional_mode_count=int(regional_mode_count),
        comm=comm,
        top_orthogonality_defect=float(defect),
        physical_row_keys=physical_keys,
        active_row_positions=active_row_positions,
        row_order_audit=row_order_audit,
    )
    del gram, factor, normalization, raw_top, top_gram
    return basis


class _PackedCholesky:
    def __init__(self, matrix: np.ndarray):
        self.rows = int(matrix.shape[0])
        lower = np.linalg.cholesky(matrix)
        self.packed = np.ascontiguousarray(
            lower[np.tril_indices(self.rows)], dtype=np.complex128
        )
        reconstructed = self.lower()
        self.factorization_relative_error = _relative(
            reconstructed @ reconstructed.conj().T - matrix, matrix
        )

    def lower(self) -> np.ndarray:
        lower = np.zeros((self.rows, self.rows), dtype=np.complex128)
        lower[np.tril_indices(self.rows)] = self.packed
        return lower

    def solve(self, right_hand_side: np.ndarray) -> np.ndarray:
        lower = self.lower()
        first = np.linalg.solve(lower, np.asarray(right_hand_side))
        return np.linalg.solve(lower.conj().T, first)

    @property
    def nbytes(self) -> int:
        return int(self.packed.nbytes)


def _m_inner(left: np.ndarray, mass: np.ndarray, right: np.ndarray) -> complex:
    return complex(np.vdot(left, mass @ right))


def _m_orthonormalize(
    candidate: np.ndarray,
    previous: Sequence[np.ndarray],
    mass: np.ndarray,
    label: str,
) -> np.ndarray:
    value = np.asarray(candidate, dtype=np.complex128).copy()
    for base in previous:
        value -= base * _m_inner(base, mass, value)
    norm_squared = _m_inner(value, mass, value).real
    if not np.isfinite(norm_squared) or norm_squared <= N1_DEPENDENCY_TOL**2:
        raise RuntimeError(
            f"{label} is linearly dependent after constraints: "
            f"mass_norm={norm_squared} limit={N1_DEPENDENCY_TOL**2}"
        )
    return value / np.sqrt(norm_squared)


def canonicalize_degenerate_eigenvectors(
    eigenvalues: np.ndarray,
    eigenvectors: np.ndarray,
    mass: np.ndarray,
    operator: np.ndarray,
    row_keys: Sequence[Any],
    selected_indices: Sequence[int],
) -> tuple[np.ndarray, tuple[float, ...], tuple[int, ...]]:
    """Choose canonical vectors inside fixed machine-scale eigenspace clusters.

    ``eigenvectors`` are generalized eigenvectors in physical coordinates and
    are M-orthonormal.  A cluster is anchored by projecting coordinate vectors
    ordered by canonical row key into the complete cluster, then applying the
    same M-orthogonalization and phase rule.  Only the requested prefix is
    returned; the full cluster is canonicalized before a prefix is taken.
    """

    values = np.asarray(eigenvalues, dtype=np.float64)
    vectors = np.asarray(eigenvectors, dtype=np.complex128)
    metric = np.asarray(mass, dtype=np.complex128)
    matrix = np.asarray(operator, dtype=np.complex128)
    selected = tuple(int(index) for index in selected_indices)
    if not selected:
        return np.empty((vectors.shape[0], 0), dtype=np.complex128), (), ()
    scale = max(float(np.max(np.abs(values), initial=0.0)), 1.0)
    cluster_tolerance = (
        N1_DEGENERATE_CLUSTER_ULPS * np.finfo(np.float64).eps * scale
    )
    clusters: list[tuple[int, int]] = []
    start = 0
    for index in range(1, values.size):
        if abs(values[index] - values[index - 1]) > cluster_tolerance:
            clusters.append((start, index))
            start = index
    clusters.append((start, int(values.size)))
    selected_by_index: dict[int, tuple[np.ndarray, float]] = {}
    row_order = tuple(sorted(range(len(row_keys)), key=lambda row: repr(row_keys[row])))
    selected_set = set(selected)
    anchor_dependency_limit = (
        N1_DEGENERATE_CLUSTER_ULPS * np.finfo(np.float64).eps
    ) ** 2
    for cluster_start, cluster_stop in clusters:
        cluster_indices = tuple(range(cluster_start, cluster_stop))
        if not selected_set.intersection(cluster_indices):
            continue
        cluster_vectors = vectors[:, cluster_start:cluster_stop]
        anchored: list[np.ndarray] = []
        for row in row_order:
            projected = cluster_vectors @ (
                cluster_vectors.conj().T @ metric[:, row]
            )
            for previous in anchored:
                projected -= previous * _m_inner(previous, metric, projected)
            norm_squared = _m_inner(projected, metric, projected).real
            if norm_squared <= anchor_dependency_limit:
                continue
            projected = projected / np.sqrt(norm_squared)
            phase_candidates = [
                candidate
                for candidate, value in enumerate(projected)
                if abs(value) > N1_PHASE_ZERO
            ]
            if not phase_candidates:
                continue
            max_amplitude = max(abs(projected[candidate]) for candidate in phase_candidates)
            phase_tie = (
                N1_DEGENERATE_CLUSTER_ULPS
                * np.finfo(np.float64).eps
                * max(1.0, float(max_amplitude))
            )
            anchor = next(
                candidate
                for candidate in row_order
                if candidate in phase_candidates
                and abs(projected[candidate]) >= max_amplitude - phase_tie
            )
            projected *= np.exp(-1j * np.angle(projected[anchor]))
            anchored.append(projected)
            if len(anchored) == len(cluster_indices):
                break
        if len(anchored) != len(cluster_indices):
            raise RuntimeError(
                "canonical eigenspace anchors did not span cluster: "
                f"size={len(cluster_indices)} found={len(anchored)}"
            )
        for local, original_index in enumerate(cluster_indices):
            if original_index not in selected_set:
                continue
            vector = anchored[local]
            denominator = _m_inner(vector, metric, vector)
            quotient = _m_inner(vector, matrix, vector) / denominator
            selected_by_index[original_index] = (vector, float(quotient.real))
    output_vectors = np.column_stack(
        [selected_by_index[index][0] for index in selected]
    )
    output_values = tuple(selected_by_index[index][1] for index in selected)
    selected_cluster_sizes = tuple(
        cluster_stop - cluster_start
        for cluster_start, cluster_stop in clusters
        if selected_set.intersection(range(cluster_start, cluster_stop))
    )
    return output_vectors, output_values, selected_cluster_sizes


class LocalSpectralPatch:
    """One fixed-cell constrained B0/M_local spectral patch.

    ``row_keys`` are the complete local cell-supported constrained rows.  The
    optional multiplicity is the number of patches containing each canonical
    row; its reciprocal is the only PoU weight used here.
    """

    def __init__(
        self,
        block: np.ndarray,
        local_mass: np.ndarray,
        gradient_candidates: np.ndarray,
        *,
        patch_id: int,
        exact_class_digest: str,
        row_keys: Iterable[Any],
        shared_row_multiplicity: np.ndarray | None = None,
        comm: Any = MPI.COMM_WORLD,
        class_plan: ExactClassOwnerPlan | None = None,
    ) -> None:
        self.comm = comm
        self.patch_id = int(patch_id)
        self.class_digest = _class_digest(exact_class_digest)
        self.block = np.ascontiguousarray(np.asarray(block, dtype=np.complex128))
        self.local_mass = np.ascontiguousarray(
            np.asarray(local_mass, dtype=np.complex128)
        )
        self.gradient_candidates = np.ascontiguousarray(
            np.asarray(gradient_candidates, dtype=np.complex128)
        )
        self.row_keys = tuple(row_keys)
        if class_plan is None:
            class_plan = ExactClassOwnerPlan((self.class_digest,), comm)
        self.class_plan = class_plan
        self._modes: np.ndarray | None = None
        self._audit: dict[str, Any] = {}
        self._destroyed = False
        self._construction_released = False
        self._validate_shapes()
        if shared_row_multiplicity is None:
            multiplicity = np.ones(self.block.shape[0], dtype=np.int64)
        else:
            multiplicity = np.asarray(shared_row_multiplicity, dtype=np.int64).copy()
        if multiplicity.shape != (self.block.shape[0],) or np.any(multiplicity < 1):
            raise ValueError("row multiplicity must be a positive local vector")
        self._row_multiplicity = multiplicity
        self._pou_weights = 1.0 / multiplicity.astype(np.float64)
        self._row_count = int(self.block.shape[0])

    @classmethod
    def from_mode_template(
        cls,
        mode_shard: np.ndarray,
        *,
        patch_id: int,
        exact_class_digest: str,
        row_keys: Iterable[Any],
        shared_row_multiplicity: np.ndarray | None = None,
        comm: Any = MPI.COMM_WORLD,
        class_plan: ExactClassOwnerPlan | None = None,
        class_template_row_keys: Iterable[Any] | None = None,
    ) -> "LocalSpectralPatch":
        """Create a retained patch shard without a second dense eigensolve."""

        modes = np.ascontiguousarray(np.asarray(mode_shard, dtype=np.complex128))
        keys = tuple(row_keys)
        if modes.ndim != 2 or modes.shape[1] != N1_MODE_CAP:
            raise ValueError("retained mode shard must have eight columns")
        if modes.shape[0] > N1_MAX_LOCAL_ROWS or len(keys) != modes.shape[0]:
            raise ValueError("retained mode shard exceeds the local row contract")
        if len(set(keys)) != len(keys) or not np.all(np.isfinite(modes)):
            raise ValueError("retained mode shard keys or values are invalid")
        if class_plan is None:
            class_plan = ExactClassOwnerPlan((exact_class_digest,), comm)
        obj = cls.__new__(cls)
        obj.comm = comm
        obj.patch_id = int(patch_id)
        obj.class_digest = _class_digest(exact_class_digest)
        obj.block = None
        obj.local_mass = None
        obj.gradient_candidates = None
        obj.row_keys = keys
        obj.class_plan = class_plan
        obj._modes = modes
        obj._modes.flags.writeable = False
        obj._audit = {
            "schema": "fullspace.n1.retained-class-mode-shard.v1",
            "mode_template_reused": True,
            "class_template_row_count": len(tuple(class_template_row_keys or keys)),
            "mode_template_row_count": int(modes.shape[0]),
            "mode_shard_bytes_retained": int(modes.nbytes),
            "dense_workspace_released": True,
            "construction_workspace_released": True,
            "phase_application": "maximum_amplitude_canonical_key_once_tie_by_key",
            "source_independent": True,
            "coarse_levels": N1_LEVELS,
            "regional_rank": N1_REGIONAL_RANK,
            "top_rank": N1_TOP_RANK,
            "global_numeric_allgather": False,
            "global_aij_materialized": False,
            "global_schur_materialized": False,
            "global_factor_matrix_materialized": False,
            "growing_slab_factor_materialized": False,
            "per_rank_full_basis_replication": False,
            "factor_reused": True,
            "repeat_identity": "caller_measured_class_template_reuse",
        }
        if shared_row_multiplicity is None:
            multiplicity = np.ones(modes.shape[0], dtype=np.int64)
        else:
            multiplicity = np.asarray(shared_row_multiplicity, dtype=np.int64).copy()
        if multiplicity.shape != (modes.shape[0],) or np.any(multiplicity < 1):
            raise ValueError("row multiplicity must be a positive local vector")
        obj._row_multiplicity = multiplicity
        obj._pou_weights = 1.0 / multiplicity.astype(np.float64)
        obj._row_count = int(modes.shape[0])
        obj._destroyed = False
        obj._construction_released = True
        return obj

    def _validate_shapes(self) -> None:
        rows = self.block.shape[0]
        if self.block.ndim != 2 or self.block.shape[1] != rows:
            raise ValueError("local B0 block must be square")
        if rows > N1_MAX_LOCAL_ROWS:
            raise RuntimeError(
                f"local active rows {rows} exceed limit {N1_MAX_LOCAL_ROWS}"
            )
        if self.local_mass.shape != (rows, rows):
            raise ValueError("local volumetric mass shape does not match B0")
        if self.gradient_candidates.shape != (rows, N1_GRADIENT_COUNT):
            raise ValueError("exactly three full local gradient candidates are required")
        if len(self.row_keys) != rows:
            raise ValueError("canonical row key count does not match local rows")
        if len(set(self.row_keys)) != rows:
            raise ValueError("local canonical row keys are duplicated")
        if not np.all(np.isfinite(self.block)):
            raise ValueError("local B0 block is non-finite")
        if not np.all(np.isfinite(self.local_mass)):
            raise ValueError("local volumetric mass is non-finite")
        if not np.all(np.isfinite(self.gradient_candidates)):
            raise ValueError("gradient candidates are non-finite")
        block_defect = _hermitian_defect(self.block)
        mass_defect = _hermitian_defect(self.local_mass)
        if block_defect > N1_ALGEBRA_LIMIT:
            raise RuntimeError(
                f"B0 Hermitian defect {block_defect} exceeds limit {N1_ALGEBRA_LIMIT}"
            )
        if mass_defect > N1_ALGEBRA_LIMIT:
            raise RuntimeError(
                f"M_local Hermitian defect {mass_defect} exceeds limit "
                f"{N1_ALGEBRA_LIMIT}"
            )
        if float(np.min(np.linalg.eigvalsh(self.block))) <= 0.0:
            raise RuntimeError("local B0 is not positive definite")
        if float(np.min(np.linalg.eigvalsh(self.local_mass))) <= 0.0:
            raise RuntimeError("local volumetric mass is not positive definite")

    @property
    def modes(self) -> np.ndarray:
        if self._modes is None:
            raise RuntimeError("local spectral patch has not been built")
        view = self._modes.view()
        view.flags.writeable = False
        return view

    @property
    def audit(self) -> Mapping[str, Any]:
        return MappingProxyType(self._audit)

    def _phase_fix(self, vector: np.ndarray) -> np.ndarray:
        candidates = [
            (-abs(value), str(self.row_keys[index]), index)
            for index, value in enumerate(vector)
            if abs(value) > N1_PHASE_ZERO
        ]
        if not candidates:
            raise RuntimeError("local mode has no nonzero canonical phase anchor")
        _amplitude, _key, index = min(candidates)
        return vector * np.exp(-1j * np.angle(vector[index]))

    def _build_modes(self) -> tuple[np.ndarray, dict[str, Any]]:
        stiffness = self.block
        mass = self.local_mass
        mass_cholesky = np.linalg.cholesky(mass)
        gradient_modes: list[np.ndarray] = []
        for index in range(N1_GRADIENT_COUNT):
            gradient_modes.append(
                _m_orthonormalize(
                    self.gradient_candidates[:, index],
                    gradient_modes,
                    mass,
                    f"gradient candidate {index}",
                )
            )
        gradient_matrix = np.column_stack(
            [self._phase_fix(value) for value in gradient_modes]
        )

        transformed_gradients = mass_cholesky.conj().T @ gradient_matrix
        _u, singular_values, vh = np.linalg.svd(
            transformed_gradients.conj().T, full_matrices=True
        )
        minimum = float(np.min(singular_values)) if singular_values.size else 0.0
        if singular_values.size < N1_GRADIENT_COUNT or minimum <= N1_DEPENDENCY_TOL:
            raise RuntimeError(
                f"gradient candidate rank is insufficient: min_singular={minimum} "
                f"limit={N1_DEPENDENCY_TOL}"
            )
        complement_y = vh[N1_GRADIENT_COUNT :, :].conj().T
        complement = np.linalg.solve(mass_cholesky.conj().T, complement_y)
        reduced_stiffness = complement.conj().T @ stiffness @ complement
        reduced_stiffness = (reduced_stiffness + reduced_stiffness.conj().T) * 0.5
        eigenvalues, eigenvectors = np.linalg.eigh(reduced_stiffness)
        scale = float(np.max(np.abs(eigenvalues))) if eigenvalues.size else 0.0
        positive_limit = 64.0 * np.finfo(np.float64).eps * max(1.0, scale)
        positive = [
            index
            for index, value in enumerate(eigenvalues)
            if float(value.real) > positive_limit
        ]
        if len(positive) < N1_POSITIVE_MODE_COUNT:
            raise RuntimeError(
                f"positive generalized modes {len(positive)} below required "
                f"{N1_POSITIVE_MODE_COUNT}; limit={positive_limit}"
            )
        positive_indices = tuple(positive[:N1_POSITIVE_MODE_COUNT])
        spectral_modes, spectral_values, spectral_cluster_sizes = (
            canonicalize_degenerate_eigenvectors(
                eigenvalues,
                complement @ eigenvectors,
                mass,
                stiffness,
                self.row_keys,
                positive_indices,
            )
        )
        spectral_modes = [spectral_modes[:, column] for column in range(spectral_modes.shape[1])]
        modes = np.column_stack((gradient_matrix, np.column_stack(spectral_modes)))
        projected_eigen_residual = []
        full_eigen_residual = []
        for value, eigenvalue in zip(spectral_modes, spectral_values, strict=True):
            residual = stiffness @ value - eigenvalue * (mass @ value)
            projected_eigen_residual.append(
                _relative(complement.conj().T @ residual, complement.conj().T @ stiffness @ value)
            )
            full_eigen_residual.append(_relative(residual, stiffness @ value))
        mass_gram = modes.conj().T @ mass @ modes
        mass_defect = _relative(
            mass_gram - np.eye(N1_MODE_CAP), np.eye(N1_MODE_CAP)
        )
        gradient_gram_defect = _relative(
            gradient_matrix.conj().T @ mass @ gradient_matrix
            - np.eye(N1_GRADIENT_COUNT),
            np.eye(N1_GRADIENT_COUNT),
        )
        if mass_defect > N1_ALGEBRA_LIMIT:
            raise RuntimeError(
                f"selected mode mass orthogonality {mass_defect} exceeds limit "
                f"{N1_ALGEBRA_LIMIT}"
            )
        audit = {
            "B0_hermitian_relative_defect": _hermitian_defect(stiffness),
            "M_local_hermitian_relative_defect": _hermitian_defect(mass),
            "B0_min_eigenvalue": float(np.min(np.linalg.eigvalsh(stiffness))),
            "M_local_min_eigenvalue": float(np.min(np.linalg.eigvalsh(mass))),
            "generalized_problem": "fixed_cell_constrained_B0_q_lambda_M_local_q",
            "mass_metric": "local_volumetric_k0_squared_abs_epsilon_mass",
            "generalized_eigen_residual": float(
                max(projected_eigen_residual, default=0.0)
            ),
            "full_generalized_eigen_residual_diagnostic": float(
                max(full_eigen_residual, default=0.0)
            ),
            "selected_mode_mass_orthogonality": mass_defect,
            "gradient_rank": N1_GRADIENT_COUNT,
            "gradient_m_gram_relative_defect": gradient_gram_defect,
            "selected_mode_count": int(modes.shape[1]),
            "gradient_candidate_count": N1_GRADIENT_COUNT,
            "positive_spectral_mode_count": N1_POSITIVE_MODE_COUNT,
            "positive_mode_threshold": positive_limit,
            "positive_mode_eigenvalues": spectral_values,
            "selected_spectral_cluster_sizes": spectral_cluster_sizes,
            "factorization_relative_error": None,
            "fixed_rhs_solve_residual": None,
            "factor_bytes": 0,
            "factor_bytes_limit": N1_FACTOR_BYTES_LIMIT,
            "factor_storage": "one_owner_lower_packed_complex128",
            "class_digest": self.class_digest,
            "class_owner_rank": self.class_plan.owner(self.class_digest),
            "factor_owner_local": self.class_plan.owner(self.class_digest)
            == self.comm.rank,
            "global_class_count": len(self.class_plan.class_digests),
            "row_count": int(self.block.shape[0]),
            "row_multiplicity_source": "caller_canonical_global_inverse_multiplicity",
            "pou_weight_rule": "one_over_canonical_shared_row_multiplicity",
            "pou_closure_relative_error": None,
            "restriction_prolongation_adjoint_relative_error": None,
            "phase_application": "maximum_amplitude_canonical_key_once_tie_by_key",
            "source_independent": True,
            "coarse_levels": N1_LEVELS,
            "regional_rank": N1_REGIONAL_RANK,
            "top_rank": N1_TOP_RANK,
            "global_numeric_allgather": False,
            "global_aij_materialized": False,
            "global_schur_materialized": False,
            "global_factor_matrix_materialized": False,
            "growing_slab_factor_materialized": False,
            "per_rank_full_basis_replication": False,
            "canonical_source_action_identity": "caller_measured",
            "repeat_identity": "caller_measured_independent_patch",
        }
        return modes, audit

    def build(self) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("local spectral patch has been destroyed")
        if self._construction_released:
            raise RuntimeError("local construction workspace has already been released")
        modes, audit = self._build_modes()
        audit["repeat_relative_error"] = None
        audit["repeat_exact"] = None
        owner_local = self.class_plan.owner(self.class_digest) == self.comm.rank
        factor, factor_reused = self.class_plan.ensure_factor(
            self.class_digest, self.block
        )
        if owner_local:
            assert factor is not None
            factor_audit = self.class_plan.factor_audit(self.class_digest)
            if factor_audit is None:
                raise RuntimeError("owner factor audit was not measured")
            audit.update(dict(factor_audit))
            audit["factor_reused"] = factor_reused
        else:
            audit["factor_bytes"] = 0
            audit["factorization_relative_error"] = None
            audit["factor_reused"] = None
        audit["factor_count_measured"] = self.class_plan.factor_count
        audit["total_factor_bytes_measured"] = self.class_plan.factor_bytes
        self._modes = np.ascontiguousarray(modes, dtype=np.complex128)
        self._modes.flags.writeable = False
        audit["construction_workspace_released"] = True
        self._audit = audit
        self.block = None
        self.local_mass = None
        self.gradient_candidates = None
        self._construction_released = True
        return self.modes

    def solve(
        self,
        right_hand_side: np.ndarray,
        *,
        request_id: int = 0,
        active: bool = True,
    ) -> np.ndarray:
        if self._destroyed:
            raise RuntimeError("local spectral patch has been destroyed")
        if not self._construction_released:
            raise RuntimeError("local spectral patch must be built before solve")
        rhs = np.ascontiguousarray(np.asarray(right_hand_side, dtype=np.complex128))
        if rhs.shape != (self._row_count,):
            raise ValueError("local solve RHS shape does not match B0")

        result = self.class_plan.route_solve(
            self.class_digest,
            rhs,
            request_id=request_id,
            active=active,
        )
        self._audit["last_route_request_id"] = int(request_id)
        self._audit["last_route_active"] = bool(active)
        return result

    def prolongate(self, coefficients: np.ndarray) -> np.ndarray:
        """Apply the local embedding ``P_i c = W_i Z_i c``."""

        values = np.asarray(coefficients, dtype=np.complex128)
        if values.shape != (N1_MODE_CAP,):
            raise ValueError("local coarse coefficient shape must be eight")
        return self._pou_weights * (self.modes @ values)

    def restrict(self, values: np.ndarray) -> np.ndarray:
        """Apply ``R_i x = (W_i Z_i)^H x`` under the complex inner product."""

        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self._row_count,):
            raise ValueError("local volume vector shape does not match patch rows")
        return self.modes.conj().T @ (self._pou_weights * vector)

    def restriction_prolongation_adjoint_error(
        self, values: np.ndarray, coefficients: np.ndarray
    ) -> float:
        """Measure the complex adjoint identity for one supplied pair."""

        left = np.vdot(self.restrict(values), np.asarray(coefficients))
        right = np.vdot(np.asarray(values), self.prolongate(coefficients))
        error = abs(complex(left - right)) / max(abs(complex(right)), 1.0e-300)
        self._audit["restriction_prolongation_adjoint_relative_error"] = float(error)
        return float(error)

    def pou_contribution(self, values: np.ndarray) -> tuple[tuple[Any, ...], np.ndarray]:
        """Return one owner-local canonical contribution with inverse weights."""

        vector = np.ascontiguousarray(np.asarray(values, dtype=np.complex128))
        if vector.shape != (self._row_count,):
            raise ValueError("PoU vector shape does not match local rows")
        return self.row_keys, self._pou_weights * vector

    def local_weighted_value(self, values: np.ndarray) -> np.ndarray:
        """Apply this patch's inverse multiplicity to a local vector."""

        vector = np.asarray(values, dtype=np.complex128)
        if vector.shape != (self._row_count,):
            raise ValueError("local vector shape does not match local rows")
        return self._pou_weights * vector

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._modes = None


def map_mode_template_to_patch(
    template_row_keys: Sequence[Any],
    template_modes: np.ndarray,
    patch_row_keys: Sequence[Any],
) -> np.ndarray:
    """Map class-relative template rows into one patch's canonical row order."""

    template_keys = tuple(template_row_keys)
    patch_keys = tuple(patch_row_keys)
    modes = np.asarray(template_modes, dtype=np.complex128)
    if (
        modes.ndim != 2
        or modes.shape != (len(template_keys), N1_MODE_CAP)
        or len(set(template_keys)) != len(template_keys)
        or len(set(patch_keys)) != len(patch_keys)
        or set(template_keys) != set(patch_keys)
    ):
        raise ValueError("class template and patch row keys do not match")
    index = {key: position for position, key in enumerate(template_keys)}
    mapped = np.ascontiguousarray(
        modes[np.asarray([index[key] for key in patch_keys], dtype=np.int64), :]
    )
    if not np.all(np.isfinite(mapped)):
        raise ValueError("mapped class mode shard is non-finite")
    return mapped


__all__ = (
    "ExactClassOwnerPlan",
    "LocalSpectralPatch",
    "OwnerLocalMultilevelBasis",
    "N1_FACTOR_BYTES_LIMIT",
    "N1_DEGENERATE_CLUSTER_ULPS",
    "N1_LEVELS",
    "N1_MAX_CLASSES",
    "N1_MAX_LOCAL_ROWS",
    "N1_MODE_CAP",
    "N1_PROFILE",
    "N1_REGIONAL_RANK",
    "N1_TOP_RANK",
    "N2_TOP_MIXING_SCHEMA",
    "build_owner_local_multilevel_basis",
    "canonical_pou_closure_error",
    "canonicalize_degenerate_eigenvectors",
    "canonical_vector_digest",
    "build_regional_rayleigh_ritz",
    "deterministic_class_owner",
    "deterministic_row_owner",
    "map_mode_template_to_patch",
    "packed_lower_bytes",
    "top_mixing_coefficient",
)
