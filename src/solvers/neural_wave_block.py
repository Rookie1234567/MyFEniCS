"""Block amplitude retention in the original native residual space (opt-in)."""

import json
from time import monotonic, perf_counter

import numpy as np
from scipy import linalg

from src.solvers.neural_wave_subspace import WaveSubspace, conjugate_product
from src.solvers.neural_wave_greedy import BasisStore, atomic_json, atomic_npz, sha


def compensated_columns(columns, amplitudes, batch=32):
    """Deterministic complex128 summation; no extended precision or inverse."""
    result = np.zeros(columns.shape[0], np.complex128)
    correction = np.zeros_like(result)
    for first in range(0, columns.shape[1], batch):
        value = columns[:, first : first + batch] @ amplitudes[first : first + batch]
        updated = result + value
        correction += np.where(
            abs(result) >= abs(value),
            (result - updated) + value,
            (value - updated) + result,
        )
        result = updated
    return result + correction


class BlockWaveSubspace(WaveSubspace):
    def small_basis_inner_product(self):
        old = self._small_basis_product_columns
        if self._small_basis_product is None or old > self.m:
            self._small_basis_product = conjugate_product(
                self.Q[:, : self.m], self.Q[:, : self.m]
            )
        elif self.m > old:
            cross = conjugate_product(self.Q[:, : self.m], self.Q[:, old : self.m])
            value = np.empty((self.m, self.m), np.complex128, order="F")
            value[:old, :old] = self._small_basis_product
            value[:, old:] = cross
            value[old:, :old] = cross[:old].conj().T
            self._small_basis_product = value
        self._small_basis_product_columns = self.m
        return self._small_basis_product

    def add_block(self, columns):
        if self.m >= self.capacity:
            raise ValueError("AUTHORIZED_COLUMN_CAPACITY_EXHAUSTED")
        columns = np.asarray(columns, np.complex128)
        if (
            columns.ndim != 2
            or columns.shape[0] != self.action.size
            or not np.isfinite(columns).all()
        ):
            raise ValueError("COMPLETE_FINITE_AMPLITUDE_BLOCK_REQUIRED")
        start = perf_counter()
        applied = np.column_stack(
            [self.action.apply(columns[:, j]) for j in range(columns.shape[1])]
        )
        scales = np.linalg.norm(applied, axis=0)
        nonzero = np.flatnonzero(scales > 0)
        if not len(nonzero):
            return dict(accepted=False, reason="ZERO_ACTION_BLOCK")
        normalized = applied[:, nonzero] / scales[nonzero]
        residual = self.project(normalized)
        # Exact zeros and numerically dependent directions cannot become a
        # normalized spurious basis; scientific rank threshold remains fixed.
        active = np.flatnonzero(np.linalg.norm(residual, axis=0) > self.rcond)
        if not len(active):
            return dict(accepted=False, reason="RANK_REJECTED")
        _, small, pivot = linalg.qr(residual[:, active], mode="economic", pivoting=True)
        singular = linalg.svdvals(small)
        rank = min(
            int(np.count_nonzero(singular > self.rcond * singular[0])),
            self.capacity - self.m,
        )
        if not rank:
            return dict(accepted=False, reason="RANK_REJECTED")
        selected = nonzero[active[pivot[:rank]]]
        old = self.m
        previous = (
            self.a,
            self.c,
            self.r,
            self._small_basis_product,
            self._small_basis_product_columns,
        )
        before = float(np.linalg.norm(self.r))
        mapping = np.zeros((columns.shape[1], rank), np.complex128)
        actual_rank = 0
        for j in selected:
            i = old + actual_rank
            u, z = columns[:, j] / scales[j], applied[:, j] / scales[j]
            cross = np.zeros(i, np.complex128)
            for _ in range(2):
                h = conjugate_product(self.Q[:, :i], z)
                cross += h
                z -= self.Q[:, :i] @ h
            norm = float(np.linalg.norm(z))
            if norm <= self.rcond:
                continue
            self.U[:, i], self.Q[:, i] = u, z / norm
            self.R[:i, i], self.R[i, i] = cross, norm
            mapping[j, actual_rank] = 1 / scales[j]
            actual_rank += 1
        self.seconds["orthogonalize"] += perf_counter() - start
        self.m = old + actual_rank
        if not actual_rank:
            return dict(accepted=False, reason="RANK_REJECTED")
        start = perf_counter()
        rhs = conjugate_product(self.Q[:, : self.m], self.action.f)
        used_svd = False
        try:
            self.a = linalg.solve_triangular(self.R[: self.m, : self.m], rhs)
            self.c = compensated_columns(self.U[:, : self.m], self.a)
            self.seconds["solve"] += perf_counter() - start
            start = perf_counter()
            self.r = self.action.f - self.action.apply(self.c)
            after = float(np.linalg.norm(self.r))
            self.seconds["true_residual"] += perf_counter() - start
            if not np.isfinite(after) or after > before + 1e-10 * self.action.bnorm:
                used_svd = True
                self.a = linalg.lstsq(
                    self.R[: self.m, : self.m],
                    rhs,
                    cond=self.rcond,
                    lapack_driver="gelsd",
                )[0]
                self.c = compensated_columns(self.U[:, : self.m], self.a)
                self.r = self.action.f - self.action.apply(self.c)
                after = float(np.linalg.norm(self.r))
                if not np.isfinite(after) or after > before + 1e-10 * self.action.bnorm:
                    raise ArithmeticError("SMALL_R_NUMERICAL_RANK_REJECTED")
        except Exception as error:
            self.m = old
            (
                self.a,
                self.c,
                self.r,
                self._small_basis_product,
                self._small_basis_product_columns,
            ) = previous
            self.R[:, old : old + actual_rank] = 0
            if (
                isinstance(error, ArithmeticError)
                and str(error) == "SMALL_R_NUMERICAL_RANK_REJECTED"
            ):
                return dict(
                    accepted=False,
                    reason=str(error),
                    trial_native_relative=after / self.action.bnorm,
                )
            raise
        self.pending_block = dict(
            start=old,
            stop=self.m,
            amplitude_map=mapping[:, :actual_rank],
            raw_columns=columns.shape[1],
            singular_values=singular,
            selected_raw_columns=selected[:actual_rank],
        )
        return dict(
            accepted=True,
            index=old,
            rank_added=actual_rank,
            columns=self.m,
            raw_amplitude_columns=columns.shape[1],
            numerical_rank=actual_rank,
            small_singular_values=singular.tolist(),
            rcond=self.rcond,
            new_norm=float(singular[actual_rank - 1]),
            native_relative=after / self.action.bnorm,
            actual_energy_decrease=before**2 - after**2,
            small_rank_revealing_svd_used=used_svd,
        )

    def rank_audit(self):
        # Use incremental measured Q*Q; avoid repeating a large N*m*m product.
        gram = self.small_basis_inner_product()
        return dict(
            rank=self.m,
            rank_semantics="sum of independently qualified block numerical ranks; not exact global SVD rank",
            columns=self.m,
            rcond=self.rcond,
            orthogonality=float(np.linalg.norm(gram - np.eye(self.m))),
            projected_residual=float(
                np.linalg.norm(conjugate_product(self.Q[:, : self.m], self.r))
                / self.action.bnorm
            ),
        )

    def extension_plan(self, capacity):
        # Both old and replacement buffers coexist during a safe allocation.
        return int(
            32 * self.action.size * (self.capacity + capacity)
            + 16 * (self.capacity**2 + capacity**2)
            + 2 * 2**30
        )

    def grow_capacity(self, capacity):
        if self.extension_plan(capacity) > 12 * 2**30:
            raise MemoryError("CONDITIONAL_EXTENSION_TEMPORARY_PLANNING_LINE_EXCEEDED")
        u = np.empty((self.action.size, capacity), np.complex128, order="F")
        q = np.empty_like(u)
        r = np.zeros((capacity, capacity), np.complex128, order="F")
        u[:, : self.m], q[:, : self.m], r[: self.m, : self.m] = (
            self.U[:, : self.m],
            self.Q[:, : self.m],
            self.R[: self.m, : self.m],
        )
        self.U, self.Q, self.R, self.capacity = u, q, r, capacity


class BlockBasisStore(BasisStore):
    def commit(
        self, space, model, iteration, event, rng, deadline, algorithm_state=None
    ):
        block = space.pending_block
        first, last = block["start"], block["stop"]
        suffix = ""
        chunk = self.directory / f"block_{first:05d}_{last:05d}.npz"
        if chunk.exists():
            suffix = f"_recovery_{int(monotonic() * 1e6)}"
            chunk = chunk.with_name(chunk.stem + suffix + ".npz")
        atomic_npz(
            chunk,
            u=space.U[:, first:last],
            q=space.Q[:, first:last],
            R_columns=space.R[:last, first:last],
            amplitude_map=block["amplitude_map"],
            wave_q=np.asarray(model["q"]),
            center=np.asarray(model["patch"].center),
            radius=np.asarray(model["patch"].radius),
            patch_level=np.asarray(model["patch"].level),
            selected_raw_columns=block["selected_raw_columns"],
            singular_values=block["singular_values"],
        )
        entry = dict(
            path=chunk.name,
            sha256=sha(chunk),
            start=first,
            stop=last,
            source_sha=self.binding["source_sha"],
        )
        state = self.directory / f"state_{last:05d}{suffix}.npz"
        atomic_npz(state, c=space.c, r=space.r, a=space.a)
        current = self.directory / "committed.json"
        if current.exists():
            atomic_json(
                self.directory / "previous_committed.json",
                json.loads(current.read_text()),
            )
        value = dict(
            schema="neural-wave.complete-block-boundary.v1",
            binding=self.binding,
            chunks=self.chunks + [entry],
            state=dict(path=state.name, sha256=sha(state)),
            columns=last,
            iteration=iteration,
            patch_level=model["patch"].level,
            rng_state=rng.bit_generator.state,
            remaining_seconds=deadline - monotonic(),
            event=event,
            committed=True,
            reference_used_for_training=False,
            features_reference_exposed=False,
            optimizer_state="q frozen per block; all retained amplitudes recombined after every block",
            algorithm_state=algorithm_state or {},
        )
        # Write chunks and matched coefficients before publishing the boundary.
        if sha(chunk) != entry["sha256"] or sha(state) != value["state"]["sha256"]:
            raise ValueError("ATOMIC_BLOCK_ARRAY_REOPEN_FAILED")
        atomic_json(current, value)
        # JSON canonically turns tuple coordinates into lists. Compare the
        # actual serialized value, preserving all scientific fields, rather
        # than rejecting an otherwise complete boundary on Python container type.
        if json.loads(current.read_text()) != json.loads(json.dumps(value)):
            raise ValueError("ATOMIC_BLOCK_BOUNDARY_REOPEN_FAILED")
        self.chunks.append(entry)
        return value

    def restore(self, space, rng):
        file = self.directory / "committed.json"
        if not file.exists():
            return None
        value = json.loads(file.read_text())
        if value["schema"] != "neural-wave.complete-block-boundary.v1":
            raise ValueError("BLOCK_BOUNDARY_SCHEMA_REQUIRED")
        for key in ("route", "design_sha256", "native_sha256", "moments_sha256"):
            if value["binding"].get(key) != self.binding.get(key):
                raise ValueError("RECOVERY_BINDING_MISMATCH: " + key)
        count = value["columns"]
        if count > space.capacity:
            raise ValueError("RECOVERY_CAPACITY_EXCEEDED")
        first = 0
        for entry in value["chunks"]:
            if entry["start"] != first or not first < entry["stop"] <= count:
                raise ValueError("BLOCK_COVERAGE_CORRUPT")
            path = self.directory / entry["path"]
            if sha(path) != entry["sha256"]:
                raise ValueError("RECOVERY_BLOCK_HASH_FAILED")
            last = entry["stop"]
            with np.load(path, allow_pickle=False) as a:
                space.U[:, first:last], space.Q[:, first:last] = a["u"], a["q"]
                space.R[:last, first:last] = a["R_columns"]
                if a["amplitude_map"].shape != (3 * len(a["wave_q"]), last - first):
                    raise ValueError("BLOCK_INVERSE_MAP_COVERAGE_FAILED")
            first = last
        if first != count:
            raise ValueError("BLOCK_COVERAGE_CORRUPT")
        state = self.directory / value["state"]["path"]
        if sha(state) != value["state"]["sha256"]:
            raise ValueError("RECOVERY_STATE_HASH_FAILED")
        with np.load(state, allow_pickle=False) as a:
            space.a, space.c, space.r = (np.array(a[k]) for k in ("a", "c", "r"))
        space.m = count
        if (
            np.linalg.norm(space.action.f - space.action.apply(space.c) - space.r)
            > 1e-10 * space.action.bnorm
        ):
            raise ValueError("RECOVERY_COMPLETE_RESIDUAL_FAILED")
        if np.linalg.norm(
            compensated_columns(space.U[:, :count], space.a) - space.c
        ) > 1e-10 * max(np.linalg.norm(space.c), 1e-30):
            raise ValueError("RECOVERY_COEFFICIENT_RECONSTRUCTION_FAILED")
        rng.bit_generator.state = value["rng_state"]
        self.chunks = value["chunks"]
        return value
