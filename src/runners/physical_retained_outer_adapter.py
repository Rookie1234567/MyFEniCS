"""V19 setup/evidence adapter; numerical actions remain in src.solvers."""

import hashlib
import json
import gc
import errno
import os
from pathlib import Path
import time
from time import perf_counter

import numpy as np

from .physical_p4_schur_v14 import _save_packet


BASELINE_RHS_SHA256 = "e8ece14d273d8bcdec672f2e29ac8c62971bb0d0fe4af7cc63e741df21934686"


def _array_identity(value):
    array = np.ascontiguousarray(value)
    return {"shape": list(array.shape), "dtype": str(array.dtype),
            "sha256": hashlib.sha256(memoryview(array).cast("B") if array.size else b"").hexdigest()}


def _retained_outer_scratch_workspace_bytes(
    full_rows: int, retained_rows: int
) -> int:
    """Return the existing p6 full-scratch payload estimate."""

    return int(24 * int(full_rows) * 16 + 10 * int(retained_rows) * 16)


def derive_condensed_space_identity(function_space, mpc, *, appended_rows: int):
    """Derive the expected retained-space layout from the live FE/MPC objects.

    The V21 robustness profile cannot inherit V20's fixed h10 row tuple.  This
    small pre-build calculation uses the live index map, Basix interior entity
    DoFs, and actual MPC slave rows.  It does not build a second trace expansion
    dictionary; the condensed system is later compared against this tuple in
    ``setup_checks``.
    """

    mesh = function_space.mesh
    if int(mesh.comm.size) != 1:
        raise ValueError("V21 live dimension identity is qualified for MPI1 only")
    tdim = mesh.topology.dim
    owned_cells = int(mesh.topology.index_map(tdim).size_local)
    dofmap = function_space.dofmap
    index_map = dofmap.index_map
    interior_positions = np.asarray(
        function_space.element.basix_element.entity_dofs[tdim][0],
        dtype=np.int32,
    )
    if interior_positions.size == 0:
        raise ValueError("live V21 retained space has no cell-interior DoFs")
    local_interiors = []
    local_dimensions = set()
    for cell in range(owned_cells):
        local = np.asarray(dofmap.cell_dofs(cell), dtype=np.int32)
        local_dimensions.add(int(local.size))
        original = np.asarray(
            dofmap.index_map.local_to_global(local), dtype=np.int64
        )
        local_interiors.append(original[interior_positions])
    if len(local_dimensions) != 1:
        raise ValueError("live V21 cell-local dimensions are not uniform")
    local_tensor_dimension = next(iter(local_dimensions))
    local_interior_dimension = int(interior_positions.size)
    local_trace_dimension = int(local_tensor_dimension - local_interior_dimension)
    if local_trace_dimension <= 0:
        raise ValueError("live V21 cell-local trace dimension is not positive")
    full_rows = int(index_map.size_global * dofmap.index_map_bs)
    all_interiors = (
        np.concatenate(local_interiors)
        if local_interiors
        else np.empty(0, dtype=np.int64)
    )
    if np.unique(all_interiors).size != all_interiors.size:
        raise ValueError("live V21 cell-interior DoFs are not globally unique")
    interior_rows = int(all_interiors.size)
    trace_rows = int(full_rows - interior_rows)
    local_slaves = np.unique(np.asarray(mpc.slaves, dtype=np.int64))
    owned_slaves = local_slaves[
        (local_slaves >= 0) & (local_slaves < int(index_map.size_local))
    ]
    slave_rows = np.asarray(
        index_map.local_to_global(owned_slaves.astype(np.int32)), dtype=np.int64
    )
    if np.unique(slave_rows).size != slave_rows.size:
        raise ValueError("live V21 MPC slave rows are duplicated")
    slave_master_entry_count = 0
    for local_slave in owned_slaves:
        slave_master_entry_count += int(len(mpc.masters.links(int(local_slave))))
    interior_set = set(int(value) for value in all_interiors)
    slave_set = set(int(value) for value in slave_rows)
    if interior_set.intersection(slave_set):
        raise ValueError("live V21 MPC slave rows intersect cell interiors")
    if any(value < 0 or value >= full_rows for value in slave_set):
        raise ValueError("live V21 MPC slave rows exceed the FE space")
    active_rows = int(trace_rows - len(slave_rows))
    if active_rows <= 0 or active_rows + len(slave_rows) != trace_rows:
        raise ValueError("live V21 trace/slave counts do not close")
    owned_trace = np.setdiff1d(
        np.arange(full_rows, dtype=np.int64), all_interiors, assume_unique=True
    )
    active = np.setdiff1d(
        owned_trace, slave_rows, assume_unique=True
    )
    appended_rows = int(appended_rows)
    if appended_rows < 0:
        raise ValueError("appended_rows must be non-negative")

    def digest(values) -> str:
        encoded = hashlib.sha256()
        for value in values:
            array = np.ascontiguousarray(value)
            encoded.update(str(array.shape).encode("ascii"))
            encoded.update(str(array.dtype).encode("ascii"))
            encoded.update(memoryview(array).cast("B"))
        return encoded.hexdigest()

    expected = (
        int(full_rows),
        active_rows,
        interior_rows,
        appended_rows,
    )
    facts = {
        "expected_space_counts": list(expected),
        "full_rows": int(full_rows),
        "trace_rows": int(trace_rows),
        "active_rows": active_rows,
        "slave_rows": int(len(slave_rows)),
        "slave_master_entry_count": int(slave_master_entry_count),
        "interior_rows": interior_rows,
        "appended_rows": appended_rows,
        "owned_cell_count": owned_cells,
        "local_tensor_dimension": int(local_tensor_dimension),
        "local_interior_dimension": int(local_interior_dimension),
        "local_trace_dimension": int(local_trace_dimension),
        "local_interior_dof_count": int(all_interiors.size),
        "cell_interior_dofs_sha256": digest((all_interiors,)),
        "slave_rows_sha256": digest((slave_rows,)),
        "owned_active_trace_dofs_sha256": digest((active,)),
        "source": "live_function_space_mpc_and_cell_interior_dofs",
    }
    return expected, facts


def _identity_cache_facts(system):
    """Return compact facts for the opt-in shared identity cache."""

    roles = (
        "interior_rhs_projection_by_class",
        "interior_solution_embedding_by_class",
        "interior_residual_projection_by_class",
    )
    values = [value for role in roles for value in getattr(system, role).values()]
    if not values or not all(isinstance(value, np.ndarray) for value in values):
        raise ValueError("identity cache contains an unexpected non-array projection")

    roots = {}
    for value in values:
        root = value
        while isinstance(getattr(root, "base", None), np.ndarray):
            root = root.base
        roots[id(root)] = root
    arrays = list(roots.values())
    sample = np.asarray(arrays[0])
    shape = list(sample.shape)
    dtype = str(sample.dtype)
    dimension = int(shape[0]) if len(shape) == 2 and shape[0] == shape[1] else -1
    if dimension < 0:
        raise ValueError("identity cache arrays are not square")
    for array in arrays:
        if (
            list(array.shape) != shape
            or str(array.dtype) != dtype
            or not np.isfinite(array).all()
            or int(np.count_nonzero(array)) != dimension
            or not np.all(np.diagonal(array) == 1.0)
        ):
            raise ValueError("identity cache contains a non-identity projection")
    readonly = all(not array.flags.writeable for array in arrays)
    if not readonly:
        raise ValueError("shared identity cache arrays must be readonly")

    audit = system.build_audit
    mode = str(audit["identity_cache_mode"])
    logical_class_count = len(system.interior_rhs_projection_by_class)
    representation = {
        "mode": mode,
        "read_only": readonly,
        "shape": shape,
        "dtype": dtype,
        "logical_class_count": logical_class_count,
        "unique_storage_count": len(arrays),
        "unique_storage_bytes": int(sum(array.nbytes for array in arrays)),
    }
    semantic = {
        "operator": "identity",
        "shape": shape,
        "dtype": dtype,
        "roles": list(roles),
        "logical_class_count": logical_class_count,
        "dimension": dimension,
    }
    digest = lambda value: hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "semantic": semantic,
        "semantic_sha256": digest(semantic),
        "representation_sha256": digest(representation),
        "representation": representation,
    }


def _cache_identity(action, *, include_identity=False):
    """Hash this component's actual arrays and count aliased storage once."""
    system = action.condensed
    arrays = {}
    for name in ("interior_lu_by_class", "interior_from_trace_by_class",
                 "trace_from_interior_rhs_by_class", "interior_rhs_projection_by_class",
                 "interior_solution_embedding_by_class", "interior_residual_projection_by_class",
                 "retained_local_schur_by_class"):
        for key, values in getattr(system, name).items():
            for index, value in enumerate(values if isinstance(values, tuple) else (values,)):
                arrays[f"{name}/{key!r}/{index}"] = value
    arrays["trace_original"] = system.owned_trace_original_dofs
    arrays["active_original"] = system.trace_constraints.owned_active_original_dofs
    for index, cell in enumerate(action._cells):
        for name in ("original_interiors", "original_trace", "active_ids", "ports",
                     "Bi", "Bt", "Di", "Dt", "Bhat", "Dhat", "XiB", "Hlocal"):
            arrays[f"cell/{index}/{name}"] = getattr(cell, name)
        for name in ("data", "indices", "indptr"):
            arrays[f"cell/{index}/expansion/{name}"] = getattr(cell.expansion, name)
    for name in ("_H_p", "_Hhat"):
        arrays[name] = getattr(action, name)
    for name in ("_direct_B_original", "_direct_D_original", "_direct_B_active", "_direct_D_active"):
        for port, pair in getattr(action, name).items():
            for index, value in enumerate(pair):
                arrays[f"{name}/{port}/{index}"] = value
    unique, groups = {}, {}
    identities = {}
    trace_digest = hashlib.sha256()
    for original, pair in sorted(system.trace_constraints.expansion_by_original.items()):
        trace_digest.update(str(original).encode() + b"\n")
        for value in pair:
            contiguous = np.ascontiguousarray(value)
            trace_digest.update(str(contiguous.shape).encode() + str(contiguous.dtype).encode())
            trace_digest.update(memoryview(contiguous).cast("B"))
            base = value
            while isinstance(base.base, np.ndarray):
                base = base.base
            if id(base) not in unique:
                unique[id(base)] = int(base.nbytes)
                groups["trace_expansion"] = groups.get("trace_expansion", 0) + int(base.nbytes)
    identities["trace_expansion"] = {"sha256": trace_digest.hexdigest(),
                                      "row_count": len(system.trace_constraints.expansion_by_original)}
    for name, value in arrays.items():
        base = value
        while isinstance(base.base, np.ndarray):
            base = base.base
        if id(base) not in unique:
            unique[id(base)] = int(base.nbytes)
            groups[name.split("/")[0]] = groups.get(name.split("/")[0], 0) + int(base.nbytes)
        identities[name] = _array_identity(value)
    # Keep detailed maps in a packet, and a single recipe digest in summaries.
    digest = hashlib.sha256(json.dumps(identities, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = {"arrays": identities, "array_content_sha256": digest,
              "unique_numpy_bytes": sum(unique.values()), "components": groups,
              "scatter_vectors_bytes": 0,
              "scope": "resident numerical payload; Python/PETSc allocator overhead measured by full tree RSS"}
    if include_identity:
        identity_cache = _identity_cache_facts(system)
        result.update(
            {
                "identity_cache": identity_cache,
                "identity_cache_semantic_sha256": identity_cache[
                    "semantic_sha256"
                ],
                "identity_cache_representation_sha256": identity_cache[
                    "representation_sha256"
                ],
            }
        )
    return result


class RetainedOuterAdapter:
    def __init__(
        self,
        runtime,
        common,
        resolved,
        full_rhs,
        apply_pc,
        *,
        p4_identity_sha256,
        pc_counts,
        compiled_form=None,
        identity_cache_mode="per_oriented_class",
        evidence_prefix="v19",
        expected_space_counts=(173802, 51192, 113400, 80),
        expected_space_facts=None,
        rhs_identity_policy="fixed_historical_contract",
        save_complete_field_packet=None,
        p4_count_policy="legacy_one_mat_solve_per_logical",
        first_direction_pair_context=None,
    ):
        self.runtime, self.common, self.resolved = runtime, common, resolved
        self.full_rhs, self.bal_h = full_rhs, apply_pc
        self.p4_identity_sha256 = p4_identity_sha256
        self.pc_counts = pc_counts
        self.compiled_form = compiled_form
        self.identity_cache_mode = str(identity_cache_mode)
        self.evidence_prefix = str(evidence_prefix)
        self.save_complete_field_packet = (
            self.evidence_prefix in {"v20", "v21"}
            if save_complete_field_packet is None
            else bool(save_complete_field_packet)
        )
        self.expected_space_counts = (
            None
            if expected_space_counts is None
            else tuple(int(value) for value in expected_space_counts)
        )
        self.expected_space_facts = (
            None if expected_space_facts is None else dict(expected_space_facts)
        )
        self.rhs_identity_policy = str(rhs_identity_policy)
        self.p4_count_policy = str(p4_count_policy)
        self.first_direction_pair_context = first_direction_pair_context
        if self.p4_count_policy not in {
            "legacy_one_mat_solve_per_logical",
            "bounded_repair_v24",
        }:
            raise ValueError(f"unsupported p4 count policy: {self.p4_count_policy}")
        if self.rhs_identity_policy not in {
            "fixed_historical_contract",
            "case_bound_physical_rhs",
        }:
            raise ValueError(
                f"unsupported RHS identity policy: {self.rhs_identity_policy}"
            )
        if self.identity_cache_mode not in {
            "per_oriented_class",
            "shared_read_only_per_interior_shape",
        }:
            raise ValueError(f"unsupported identity cache mode: {self.identity_cache_mode}")
        self.action = self.rhs = self.condensed = None
        self.full_source = self.full_target = None
        self.last_evaluation = None
        self.identity = {}
        self.checks = {}
        self.residual_packets = []
        self.retained_checkpoints = {}
        self._final_packet_saved = False
        self._released_after_final_residual = False
        self._released_facts = None
        self.actual_first_arnoldi = {}
        self._active_role = "setup"
        self.role_counts = {
            role: {"schur_action": 0, "bridge": 0, "native_action": 0}
            for role in ("setup", "iteration", "check")
        }
        self.role_timings = {role: 0.0 for role in ("setup", "iteration", "check")}
        self.time = {"setup_seconds": 0.0, "schur_action_seconds": 0.0,
                     "bridge_seconds": 0.0, "bal_h_seconds": 0.0,
                     "native_action_seconds": 0.0, "recovery_evaluation_seconds": 0.0,
                     "packet_seconds": 0.0}
        self.count = {"schur_action": 0, "bridge": 0, "native_action": 0}

    def _count(self, name):
        if name not in self.count:
            raise KeyError(f"unknown retained adapter counter: {name}")
        self.count[name] += 1
        self.role_counts[self._active_role][name] += 1

    def _record_role_time(self, started):
        self.role_timings[self._active_role] += perf_counter() - started

    def build(self):
        from dolfinx import fem
        from src.solvers.hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation
        from src.solvers.p6_cell_condensed_action import (
            build_p6_cell_condensed_action_from_carrier, P6RetainedBALHBridge,
        )
        runtime, levels = self.runtime, self.common["levels"]
        started = perf_counter()
        prefix = self.evidence_prefix
        compiled_form = self.compiled_form
        owns_compiled_form = compiled_form is None
        if compiled_form is None:
            compiled_form = fem.form(self.common["fine"]["volume_action"].bilinear_form)

        def allocation_gate(name, facts):
            if name != "cell_tensor_working_set":
                raise ValueError("V19 p6 unexpectedly requested global matrix storage")
            amount = int(facts["retained_numeric_bytes_upper"])
            runtime.check_inventory_projected(f"{prefix}_p6_local_caches", amount)
            runtime.check_projected(f"{prefix}_p6_local_caches", amount, workspace_bytes=int(facts["workspace_bytes"]))
            runtime.reserve_workspace(f"{prefix}_p6_setup", int(facts["workspace_bytes"]))

        runtime.marker(f"{prefix}_p6_local_setup_started", {"global_matrix": False})
        self.condensed = build_unconstrained_assembly_time_condensation(
            compiled_form,
            levels["spaces"][6], levels["mesh_data"].cell_tags, mpc=levels["floquets"][6].mpc,
            appended_global_rows=len(self.common["fine"]["dtn_action"].carrier.entries),
            sum_duplicate_cell_integrals=True, strict_local_checks=True,
            materialize_global_matrix=False, retain_local_schur_for_matrix_free=True,
            share_identity_cache=(self.identity_cache_mode == "shared_read_only_per_interior_shape"),
            allocation_gate=allocation_gate,
        )
        runtime.release_workspace(f"{prefix}_p6_setup")
        runtime.reserve_workspace(f"{prefix}_p6_setup", 128 << 20)
        self.action = build_p6_cell_condensed_action_from_carrier(
            self.condensed, self.common["fine"]["dtn_action"].carrier,
        )
        shared_identity_mode = (
            self.identity_cache_mode == "shared_read_only_per_interior_shape"
        )
        cache = _cache_identity(self.action, include_identity=shared_identity_mode)
        if shared_identity_mode:
            identity_facts = cache["identity_cache"]
            if not (
                identity_facts["semantic"]["operator"] == "identity"
                and identity_facts["representation"]["read_only"] is True
                and identity_facts["representation"]["unique_storage_count"] == 1
            ):
                raise ValueError(
                    "shared identity cache is not a verified readonly identity"
                )
        if shared_identity_mode:
            self.condensed.build_audit.update(
                {
                    "identity_cache_semantic_sha256": cache[
                        "identity_cache_semantic_sha256"
                    ],
                    "identity_cache_representation_sha256": cache[
                        "identity_cache_representation_sha256"
                    ],
                    "identity_cache_representation": cache["identity_cache"][
                        "representation"
                    ],
                }
            )
        runtime.reserve_inventory(f"{prefix}_p6_local_caches", {
            "unique_numeric_arrays": cache["unique_numpy_bytes"],
            "scatter_vectors": cache["scatter_vectors_bytes"],
        }, check_rss=False)
        self.identity = {
            "source_sha": runtime.source_sha, "degree": 6,
            "physical_model_sha256": self.resolved["provenance"]["physical_model_sha256"],
            "ordered_mode_sha256": self.common["fine"]["mode_sha256"],
            "p4_operator_identity_sha256": self.p4_identity_sha256,
            "p6_recipe": dict(self.action.operator_recipe),
            "p6_array_content_sha256": cache["array_content_sha256"],
            "p6_build_audit": self.condensed.build_audit,
        }
        from src.runners.physical_macro_controls import _mapping_identity_sha256
        from src.solvers.condensed_fine_reference import native_map_arrays

        p6_native_map = native_map_arrays(
            levels["spaces"][6], levels["floquets"][6]
        )
        self.identity["p6_native_map_sha256"] = _mapping_identity_sha256(
            p6_native_map
        )
        self.identity["p6_native_map_array_facts"] = {
            key: _array_identity(value)
            for key, value in sorted(p6_native_map.items())
            if isinstance(value, np.ndarray)
        }
        del p6_native_map
        if self.expected_space_facts is not None:
            self.identity["expected_space_facts"] = dict(self.expected_space_facts)
        if shared_identity_mode:
            self.identity.update(
                {
                    "identity_cache_mode": self.identity_cache_mode,
                    "compiled_form_reused": not owns_compiled_form,
                    "p6_identity_cache_semantic_sha256": cache[
                        "identity_cache_semantic_sha256"
                    ],
                    "p6_identity_cache_representation_sha256": cache[
                        "identity_cache_representation_sha256"
                    ],
                }
            )
        cache_packet_name = (
            "x1_p6_cache_identity"
            if prefix == "v19"
            else f"{prefix}_x1_p6_cache_identity"
        )
        self._packet(cache_packet_name, {"identity": self.identity, "cache": cache})
        self.cache = {k: v for k, v in cache.items() if k != "arrays"}
        runtime.release_workspace(f"{prefix}_p6_setup")
        # Simultaneous full scratch, residual packet arrays, bridge outputs,
        # and the fixed three-vector setup fixture; the Krylov pool is separate.
        scratch_bytes = _retained_outer_scratch_workspace_bytes(
            int(self.full_rhs.getLocalSize()), self.action.reduced_size
        )
        runtime.reserve_workspace(f"{prefix}_p6_full_scratch", scratch_bytes)
        self.full_source, self.full_target = self.full_rhs.duplicate(), self.full_rhs.duplicate()
        self.rhs = self.action.create_reduced_rhs_vector()
        self.rhs.array[:] = self.action.reduce_rhs(self.full_rhs, rhs_is_mpc_dual=True)
        self.bridge = P6RetainedBALHBridge(self.action, self._bal_h_array)
        self.time["setup_seconds"] = perf_counter() - started
        runtime.marker(f"{prefix}_p6_local_setup_complete", {"identity": self.identity, "cache": self.cache})
        if owns_compiled_form:
            del compiled_form
        self.compiled_form = None

    def _packet(self, name, facts):
        started = perf_counter()
        packet = _save_packet(self.runtime.directory, name, facts, runtime=self.runtime)
        self.time["packet_seconds"] += perf_counter() - started
        return packet

    def _bal_h_array(self, source):
        started = perf_counter()
        self.full_source.array[:] = source
        result = self.bal_h(self.full_source)
        try:
            return result.array_r.copy()
        finally:
            result.destroy()
            self.time["bal_h_seconds"] += perf_counter() - started

    def _native_array(self, source):
        started = perf_counter()
        self.full_source.array[:] = source
        self.common["fine"]["physical_action"].apply(self.full_source, self.full_target)
        self._count("native_action")
        self.time["native_action_seconds"] += perf_counter() - started
        self._record_role_time(started)
        return self.full_target.array_r.copy()

    def _apply(self, source):
        started = perf_counter()
        result = self.action.apply(source)
        self._count("schur_action")
        self.time["schur_action_seconds"] += perf_counter() - started
        self._record_role_time(started)
        return result

    def _pc(self, source):
        started = perf_counter()
        values = self.bridge.apply(source.array_r)
        result = source.duplicate()
        try:
            result.array[:] = values
        except BaseException:
            result.destroy()
            raise
        self._count("bridge")
        self.time["bridge_seconds"] += perf_counter() - started
        self._record_role_time(started)
        return result

    def _evaluate(self, source, _schur_residual):
        previous_role = self._active_role
        self._active_role = "check"
        started = perf_counter()
        try:
            # Previous residual arrays have already been saved.  Drop them before
            # constructing the next packet so two full evaluation sets never live
            # simultaneously under the single scratch reservation.
            self.last_evaluation = None
            self.last_evaluation = self.action.evaluate_native_residual(
                source.array_r, self.full_rhs, self._native_array,
                rhs_is_mpc_dual=True,
                reduced_residual=None if _schur_residual is None else _schur_residual.array_r,
            )
            self.time["recovery_evaluation_seconds"] += perf_counter() - started
            facts = {key: value for key, value in self.last_evaluation.items() if not isinstance(value, np.ndarray)}
            facts["original_A6_relative"] = facts["native_residual_relative"]
            facts["port_closure_relative"] = facts["port_residual_relative"]
            facts["counts"] = dict(self.count)
            facts["resource"] = dict(
                self.runtime.sample(f"{self.evidence_prefix}_native_residual")
            )
            return facts
        finally:
            self._active_role = previous_role

    def setup_checks(self):
        started = perf_counter()
        previous_role = self._active_role
        self._active_role = "check"
        system = self.condensed
        actual = (system.full_rows, system.active_rows, system.interior_rows, system.appended_rows)
        expected = self.expected_space_counts
        if expected is None:
            raise ValueError(
                "retained outer setup requires an explicit expected space tuple"
            )
        if actual != expected:
            raise ValueError(f"derived p6 topology differs: {actual} != {expected}")
        dynamic_space_gate = bool(
            all(int(value) > 0 for value in actual[:3])
            and int(actual[3]) == len(self.common["fine"]["dtn_action"].carrier.entries)
        )
        if not dynamic_space_gate:
            raise ValueError(f"derived p6 topology is not a positive carrier-bound layout: {actual}")
        rhs_identity = _array_identity(self.full_rhs.array_r)
        if self.rhs_identity_policy == "fixed_historical_contract":
            if rhs_identity["sha256"] != BASELINE_RHS_SHA256:
                raise ValueError("new original physical RHS differs from accepted V18")
        else:
            if (
                rhs_identity["shape"] != [int(system.full_rows)]
                or rhs_identity["dtype"] != "complex128"
                or not np.isfinite(self.full_rhs.array_r).all()
            ):
                raise ValueError("case-bound physical RHS has invalid live identity")
        inputs = self.rhs.duplicate()
        output = None
        try:
            rows = []
            for index, support in enumerate(("trace", "port", "mixed")):
                # Fixed algebraic inputs, unrelated to any stored field/reference.
                k = np.arange(self.action.reduced_size)
                values = np.sin((k + 1) * 0.13) + 1j * np.cos((k + 1) * 0.17)
                if support == "trace":
                    values[system.active_rows:] = 0
                elif support == "port":
                    values[:system.active_rows] = 0
                inputs.array[:] = values
                facts = self._evaluate(inputs, None)
                passed = (facts["internal_residual_relative"] <= 1e-10
                          and facts["native_identity_relative"] <= 1e-10
                          and facts["schur_port_identity_relative"] <= 1e-10)
                packet = self._packet(f"x1_vector_{index}", {
                    "identity": self.identity, "support": support, "input": values,
                    "physical_rhs": self.full_rhs.array_r.copy(),
                    "facts": facts, "residuals": self.last_evaluation, "passed": passed,
                })
                rows.append({"support": support, "facts": facts, "packet": packet, "passed": passed})
                if not passed:
                    raise ValueError(f"X1 native recovery identity failed for {support}")
            before = dict(self.count)
            pc_before = self.pc_counts()
            output = self._pc(inputs)
            pc_after = self.pc_counts()
            pc_delta = {}
            for key, value in pc_after.items():
                before_value = pc_before.get(key)
                if isinstance(value, (int, float, np.integer, np.floating)) and isinstance(
                    before_value, (int, float, np.integer, np.floating)
                ):
                    pc_delta[key] = value - before_value
                else:
                    pc_delta[key] = value
            self._packet("x1_pc_count_check", {
                "before": pc_before, "after": pc_after, "delta": pc_delta,
                "input": inputs.array_r.copy(), "output": output.array_r.copy(),
                "source_sha": self.runtime.source_sha,
                "p4_count_policy": self.p4_count_policy,
            })
            if self.p4_count_policy == "legacy_one_mat_solve_per_logical":
                if pc_delta != {"bal_h": 1, "p4_mat_solve": 2, "h6": 1}:
                    raise ValueError(f"X1 bridge violated fixed action count: {pc_delta}")
            else:
                records = pc_after.get("p4_call_records")
                if not isinstance(records, (list, tuple)) or len(records) != 2:
                    raise ValueError(
                        "V24 X1 bridge did not expose two successful logical p4 calls"
                    )
                solve_counts = []
                for index, record in enumerate(records, 1):
                    if not isinstance(record, dict):
                        raise ValueError("V24 p4 count record is not a mapping")
                    if record.get("p4_logical_apply_count") != 1:
                        raise ValueError(
                            f"V24 p4 logical count changed for coarse call {index}"
                        )
                    repair = record.get("repair")
                    if not isinstance(repair, dict):
                        raise ValueError("V24 p4 repair ledger is missing")
                    extra = int(repair.get("extra_solve_count", -1))
                    mat_solve = record.get("p4_mat_solve_count")
                    if not 0 <= extra <= 2 or not isinstance(mat_solve, int):
                        raise ValueError("V24 p4 solve count is outside the bounded contract")
                    if mat_solve == 0 and extra != 0:
                        raise ValueError("V24 zero-RHS p4 call used a repair solve")
                    if mat_solve != 0 and mat_solve != 1 + extra:
                        raise ValueError("V24 p4 MatSolve count does not match repair count")
                    solve_counts.append(mat_solve)
                if pc_delta.get("bal_h") != 1 or pc_delta.get("h6") != 1:
                    raise ValueError(f"V24 bridge changed BAL_H/H6 count: {pc_delta}")
                if pc_delta.get("p4_mat_solve") != sum(solve_counts):
                    raise ValueError(
                        f"V24 p4 aggregate MatSolve count is inconsistent: {pc_delta} vs {solve_counts}"
                    )
            if output.getSize() != inputs.getSize() or not np.isfinite(output.array_r).all():
                raise ValueError("X1 bridge changed size or returned nonfinite data")
            self.checks = {"status": "PASS", "fixed_vector_count": 3, "vectors": rows,
                           "physical_rhs_sha256": rhs_identity["sha256"],
                           "physical_rhs_identity": rhs_identity,
                           "rhs_identity_policy": self.rhs_identity_policy,
                           "space_counts": list(actual),
                           "space_count_policy": (
                               "live_fe_mpc_cell_interior_identity"
                               if self.expected_space_facts is not None
                               else "fixed_historical_contract"
                           ),
                           "expected_space_counts": list(expected),
                           "expected_space_facts": self.expected_space_facts,
                           "actual_space_counts": list(actual),
                           "space_count_gate": dynamic_space_gate,
                           "setup_pc_calls": 1,
                           "setup_pc_input": inputs.array_r.copy(), "setup_pc_output": output.array_r.copy(),
                           "counts_before_pc": before, "counts_after_pc": dict(self.count),
                           "setup_pc_counts": pc_delta, "setup_pc_cumulative": pc_after,
                           "p4_count_policy": self.p4_count_policy,
                           "setup_seconds": perf_counter() - started,
                           "single_pc_reduction_gate": False}
            self._packet("x1_setup_checks", self.checks)
            self.checks = {k: v for k, v in self.checks.items() if not isinstance(v, np.ndarray)}
        finally:
            if output is not None:
                output.destroy()
            inputs.destroy()
            self.last_evaluation = None
            self._active_role = previous_role

    def _first_direction_pair(self, source):
        """Run the four fixed Q4 first-direction BAL_H combinations.

        The pair reuses the live factor, H6 smoother/window and one
        ``InterfaceBalancedCoupling`` instance.  Only the H6 shell's action
        is temporarily replaced by the native B6 action; both callback slots
        used by the balanced action and its ledger are swapped together and
        restored after each call.
        """

        context = self.first_direction_pair_context
        if not isinstance(context, dict):
            return None
        pc = context.get("pc")
        positive = context.get("positive")
        if pc is None or not isinstance(positive, dict):
            raise ValueError("first-direction pair context is incomplete")
        shell = positive.get("p6_shell")
        h6 = positive.get("h6")
        if shell is None or h6 is None:
            raise ValueError("first-direction pair requires the live H6 shell")
        candidate_b6 = shell.action
        candidate_a6 = getattr(pc, "_candidate_a6_callback", None)
        native_a6 = getattr(pc, "_native_a6_callback", None)
        candidate_h6 = getattr(pc, "_candidate_h6_callback", None)
        if not all(callable(value) for value in (candidate_a6, native_a6, candidate_h6)):
            raise ValueError("first-direction pair callbacks are not exposed by the live PC")
        from src.solvers.fullspace_mpc_action import FullspaceMpcFormAction

        native_started = perf_counter()
        native_b6 = None
        pair_workspace_label = f"{self.evidence_prefix}_first_direction_pair_b6"
        pair_inventory_label = f"{self.evidence_prefix}_first_direction_pair_b6"
        pair_workspace_live = False
        pair_inventory_live = False
        saved_a = saved_ledger_a = saved_s = None
        try:
            candidate_audit = dict(getattr(candidate_b6, "audit", {}))
            candidate_payload = int(
                candidate_audit.get("retained_numeric_payload_local_bytes", 0)
            )
            candidate_temporary = int(
                candidate_audit.get("per_apply_bounded_temporary_bytes", 0)
            )
            pair_workspace_bytes = max(
                1,
                candidate_payload + candidate_temporary + 16 * 1024**2,
            )
            self.runtime.reserve_workspace(pair_workspace_label, pair_workspace_bytes)
            pair_workspace_live = True
            self.runtime.reserve_inventory(
                pair_inventory_label,
                {
                    "native_b6_payload_upper_bytes": max(candidate_payload, 1),
                    "native_b6_temporary_upper_bytes": max(candidate_temporary, 0),
                },
                check_rss=False,
            )
            pair_inventory_live = True
            native_b6 = FullspaceMpcFormAction(
                candidate_b6._bilinear_form,
                candidate_b6._function_space,
                mpc=self.common["levels"]["floquets"][6].mpc,
            )
            native_setup_seconds = perf_counter() - native_started
            native_audit = dict(native_b6.audit)
            source_values = np.asarray(source.array_r).copy()
            variants = (
                ("native_a6_native_h6", native_a6, True),
                ("candidate_a6_native_h6", candidate_a6, True),
                ("native_a6_candidate_h6", native_a6, False),
                ("candidate_a6_candidate_h6", candidate_a6, False),
            )
            saved_a = pc.balanced.A
            saved_ledger_a = pc.ledger.A
            saved_s = pc.balanced.S
            callbacks_restored = False
            outputs = {}
            records = {}
            try:
                for name, a6_callback, use_native_h6 in variants:
                    pc.balanced.A = a6_callback
                    pc.ledger.A = a6_callback
                    pc.balanced.S = candidate_h6
                    shell.action = native_b6 if use_native_h6 else candidate_b6
                    before_adapter = dict(self.count)
                    before_pc = int(pc.apply_count)
                    before_native_a4 = int(pc.native_A4_count)
                    before_h6 = int(h6.apply_count)
                    before_h6_mult = int(h6.matrix_mult_count)
                    before_balanced_counts = dict(pc.balanced.total_counts)
                    before_ledger = {
                        "A_count": int(pc.ledger.A_count),
                        "PH_count": int(pc.ledger.PH_count),
                        "audit_count": int(pc.ledger.audit_count),
                    }
                    started = perf_counter()
                    result = self._pc(source)
                    try:
                        values = np.asarray(result.array_r).copy()
                    finally:
                        result.destroy()
                    after_pc = int(pc.apply_count)
                    after_native_a4 = int(pc.native_A4_count)
                    after_h6 = int(h6.apply_count)
                    after_h6_mult = int(h6.matrix_mult_count)
                    after_balanced_counts = dict(pc.balanced.total_counts)
                    after_ledger = {
                        "A_count": int(pc.ledger.A_count),
                        "PH_count": int(pc.ledger.PH_count),
                        "audit_count": int(pc.ledger.audit_count),
                    }
                    pc_facts = dict(pc.last_apply_facts)
                    coarse_records = list(pc.coarse_calls)
                    outputs[name] = values
                    records[name] = {
                        "a6_backend": (
                            "native_fullspace_action"
                            if a6_callback is native_a6
                            else "isotropic_sum_factorized_n1e_v26"
                        ),
                        "h6_backend": (
                            "native_ffcx_apply_only"
                            if use_native_h6
                            else "isotropic_sum_factorized_n1e_v26"
                        ),
                        "input_identity": _array_identity(source_values),
                        "output_identity": _array_identity(values),
                        "input_unchanged": bool(
                            np.array_equal(source_values, np.asarray(source.array_r))
                        ),
                        "elapsed_seconds": perf_counter() - started,
                        "adapter_count_before": before_adapter,
                        "adapter_count_after": dict(self.count),
                        "adapter_count_delta": {
                            key: int(self.count[key] - before_adapter[key])
                            for key in self.count
                        },
                        "pc_apply_delta": after_pc - before_pc,
                        "native_A4_delta": after_native_a4 - before_native_a4,
                        "h6_apply_delta": after_h6 - before_h6,
                        "h6_matrix_mult_delta": after_h6_mult - before_h6_mult,
                        "balanced_counts_delta": {
                            key: int(after_balanced_counts[key] - before_balanced_counts[key])
                            for key in before_balanced_counts
                        },
                        "ledger_counts_before": before_ledger,
                        "ledger_counts_after": after_ledger,
                        "component_counts": dict(pc_facts.get("counts", {})),
                        "component_seconds": dict(
                            pc_facts.get("operation_seconds", {})
                        ),
                        "p4_call_count": len(coarse_records),
                        "p4_mat_solve_count": int(
                            sum(
                                int(record.get("p4_mat_solve_count", 0) or 0)
                                for record in coarse_records
                            )
                        ),
                    }
            finally:
                shell.action = candidate_b6
                pc.balanced.A = saved_a
                pc.ledger.A = saved_ledger_a
                pc.balanced.S = saved_s
                callbacks_restored = True

            combination = outputs["candidate_a6_candidate_h6"]
            combination_norm = max(
                float(np.linalg.norm(combination)), np.finfo(float).tiny
            )
            comparisons = {}
            all_equivalent = True
            for name, values in outputs.items():
                difference = values - combination
                relative = float(np.linalg.norm(difference)) / combination_norm
                maximum = float(np.max(np.abs(difference))) if difference.size else 0.0
                passed = bool(
                    np.isfinite(values).all()
                    and records[name]["input_unchanged"]
                    and np.isfinite(relative)
                    and relative <= 1.0e-10
                )
                all_equivalent = all_equivalent and passed
                comparisons[name] = {
                    "relative_to_combination": relative,
                    "max_abs_difference": maximum,
                    "limit": 1.0e-10,
                    "passed": passed,
                }
            light_facts = dict(positive.get("light_facts", {}))
            same_input = bool(
                all(
                    record["input_identity"] == records[variants[0][0]]["input_identity"]
                    for record in records.values()
                )
            )
            summary = {
                "schema": "task039extra.v25.first-direction-a6-h6-pair.v1",
                "same_live_factor": True,
                "same_live_h6_window": True,
                "same_input": same_input,
                "input_identity": _array_identity(source_values),
                "variants": records,
                "comparisons_to_candidate_combination": comparisons,
                "passed": bool(all_equivalent and same_input and callbacks_restored),
                "native_b6_setup_seconds": native_setup_seconds,
                "native_b6_setup_backend": native_audit.get("backend"),
                "native_b6_setup_payload_local_bytes": native_audit.get(
                    "retained_numeric_payload_local_bytes"
                ),
                "h6_window": {
                    key: light_facts.get(key)
                    for key in (
                        "seed_sha256",
                        "diagonal_sha256",
                        "inverse_sqrt_diagonal_sha256",
                        "power_history",
                        "lambda_power10",
                        "lambda_lo",
                        "lambda_hi",
                    )
                },
                "no_new_factor": True,
                "no_new_pc": True,
                "used_as_initial_guess": False,
                "callbacks_restored": callbacks_restored,
                "resource_reservation": {
                    "workspace_label": pair_workspace_label,
                    "workspace_bytes": pair_workspace_bytes,
                    "inventory_label": pair_inventory_label,
                },
            }
            return {
                "summary": summary,
                "input": source_values,
                "outputs": outputs,
                "combination": combination.copy(),
            }
        finally:
            if saved_a is not None:
                pc.balanced.A = saved_a
            if saved_ledger_a is not None:
                pc.ledger.A = saved_ledger_a
            if saved_s is not None:
                pc.balanced.S = saved_s
            if native_b6 is not None:
                shell.action = candidate_b6
                native_b6.destroy()
            if pair_workspace_live:
                self.runtime.release_workspace(pair_workspace_label)
            if pair_inventory_live:
                self.runtime.release_inventory(pair_inventory_label)
            self.first_direction_pair_context = None

    def actual_first_arnoldi_check(self):
        """Probe the zero-start first right-preconditioner direction.

        With a zero initial guess, the first Arnoldi vector is the retained
        physical RHS divided by its norm.  This uses the already-built
        retained BAL_H bridge once; it does not create another factor, PC, or
        alter the KSP initial guess.
        """

        started = perf_counter()
        previous_role = self._active_role
        self._active_role = "check"
        source = self.rhs.duplicate()
        output = None
        try:
            self.rhs.copy(source)
            rhs_norm = float(self.rhs.norm())
            if not np.isfinite(rhs_norm) or rhs_norm <= np.finfo(float).tiny:
                raise ValueError("actual first Arnoldi check requires a finite nonzero RHS")
            source.scale(1.0 / rhs_norm)
            source_values = np.asarray(source.array_r).copy()
            expected_values = np.asarray(self.rhs.array_r) / rhs_norm
            input_matches_rhs = bool(
                np.allclose(source_values, expected_values, rtol=1.0e-14, atol=1.0e-14)
            )
            before = dict(self.count)
            pair = self._first_direction_pair(source)
            if pair is None:
                output = self._pc(source)
                output_values = np.asarray(output.array_r).copy()
            else:
                output_values = np.asarray(pair["combination"]).copy()
            after = dict(self.count)
            delta = {
                key: int(after[key] - before[key]) for key in self.count
            }
            finite_output = bool(np.isfinite(output_values).all())
            size_ok = bool(
                output.getSize() == source.getSize()
                if output is not None
                else output_values.shape == source_values.shape
            )
            expected_delta = {
                "schur_action": 0,
                "bridge": 4 if pair is not None else 1,
                "native_action": 0,
            }
            passed = bool(
                input_matches_rhs
                and finite_output
                and size_ok
                and delta == expected_delta
                and (pair is None or bool(pair["summary"]["passed"]))
            )
            packet = self._packet(
                "x1_actual_first_arnoldi_right_preconditioner",
                {
                    "identity": self.identity,
                    "role": "check",
                    "input": source_values,
                    "output": output_values,
                    "rhs_norm": rhs_norm,
                    "input_norm": float(source.norm()),
                    "input_is_zero_start_retained_rhs": input_matches_rhs,
                    "used_as_initial_guess": False,
                    "bridge": type(self.bridge).__name__,
                    "count_before": before,
                    "count_after": after,
                    "count_delta": delta,
                    "expected_count_delta": expected_delta,
                    "pair": None if pair is None else pair["outputs"],
                    "pair_summary": None if pair is None else pair["summary"],
                    "passed": passed,
                },
            )
            self.actual_first_arnoldi = {
                "schema": "task039extra.v25.actual-first-arnoldi-check.v1",
                "role": "check",
                "rhs_norm": rhs_norm,
                "input_norm": float(source.norm()),
                "input_identity": _array_identity(source_values),
                "output_identity": _array_identity(output_values),
                "input_is_zero_start_retained_rhs": input_matches_rhs,
                "used_as_initial_guess": False,
                "bridge": type(self.bridge).__name__,
                "new_pc_or_factor": False,
                "count_before": before,
                "count_after": after,
                "count_delta": delta,
                "expected_count_delta": expected_delta,
                "finite_output": finite_output,
                "size_ok": size_ok,
                "packet": packet,
                "pair": None if pair is None else pair["summary"],
                "passed": passed,
                "elapsed_seconds": perf_counter() - started,
            }
            if not passed:
                raise RuntimeError(
                    "actual first Arnoldi retained bridge check failed: "
                    f"{self.actual_first_arnoldi}"
                )
            return dict(self.actual_first_arnoldi)
        finally:
            if output is not None:
                output.destroy()
            source.destroy()
            self._active_role = previous_role

    def solve(self, *, checkpoint, append, seconds, resource_sample, stop_requested):
        from src.solvers.physical_retained_fgmres import run_retained_fgmres

        previous_role = self._active_role
        self._active_role = "iteration"

        def save_retained(iteration, y):
            self.retained_checkpoints[iteration] = self._packet(f"x2_y_{iteration:04d}", {
                "identity": self.identity, "iteration": iteration, "retained_y": y.array_r.copy(),
                "saved_before_field_evaluation": True,
            })

        def save_row(name, row):
            if name == "monitor_residuals.jsonl":
                iteration = row["iteration"]
                raw = {key: self.last_evaluation[key] for key in (
                    "native_residual", "augmented_port_residual", "internal_residual",
                    "schur_residual", "native_identity_difference",
                    "schur_port_identity_difference",
                )}
                packet = self._packet(f"x2_residual_{iteration:04d}_{len(self.residual_packets):04d}",
                                      {"identity": self.identity, "facts": row, "raw": raw})
                self.residual_packets.append(packet)
                row = {**row, "packet": packet}
            append(name, row)

        def full_checkpoint(iteration, y, row):
            # save_retained has already committed y, including terminal exits.
            self.full_target.array[:] = self.last_evaluation["storage_solution"]
            return checkpoint(iteration, self.full_target, row["original_A6_relative"])

        try:
            result = run_retained_fgmres(
                self.rhs, self._apply, self._pc, evaluate=self._evaluate,
                checkpoint=full_checkpoint, save_retained=save_retained, append=save_row, seconds=seconds,
                resource_sample=resource_sample, stop_requested=stop_requested,
            )
        finally:
            self._active_role = previous_role
        post_ksp_started_ns = time.perf_counter_ns()
        y = result.pop("final_solution")
        try:
            cache_after = _cache_identity(
                self.action,
                include_identity=(
                    self.identity_cache_mode
                    == "shared_read_only_per_interior_shape"
                ),
            )
            if cache_after["array_content_sha256"] != self.cache["array_content_sha256"]:
                raise ValueError("p6 condensation cache content changed across outer calls")
            if cache_after["unique_numpy_bytes"] != self.cache["unique_numpy_bytes"]:
                raise ValueError("p6 condensation cache payload grew across calls")
            result["p6_cache_after"] = {k: v for k, v in cache_after.items() if k != "arrays"}
            result["actual_pc_counts_including_one_setup_call"] = self.pc_counts()
            final_packet = {
                "identity": self.identity,
                "retained_y": y.array_r.copy(),
                "physical_rhs": self.full_rhs.array_r.copy(),
                "saved_before_field_evaluation": True,
                "facts": result["final_evaluation"],
                "residuals": self.last_evaluation,
            }
            if self.save_complete_field_packet:
                from src.solvers.fullspace_physical_intermediate_runtime import (
                    owned_slave_indices,
                )

                final_packet.update(
                    {
                        "original_rhs": self.full_rhs.array_r.copy(),
                        "full_solution": np.asarray(
                            self.last_evaluation["storage_solution"],
                            dtype=np.complex128,
                        ).copy(),
                        "owned_slave_rows": owned_slave_indices(
                            self.common["levels"]["spaces"][6],
                            self.common["levels"]["floquets"][6],
                        ),
                        "complete_field_saved": True,
                    }
                )
            self._packet("x2_retained_final", final_packet)
            self._final_packet_saved = True
            if self.save_complete_field_packet:
                self.runtime.marker(
                    (
                        "v20_complete_field_packet_saved"
                        if self.evidence_prefix in {"v20", "v21"}
                        else f"{self.evidence_prefix}_complete_field_packet_saved"
                    ),
                    {
                        "packet": "x2_retained_final.json",
                        "retained_y_saved": True,
                        "original_rhs_saved": True,
                        "full_solution_saved": True,
                    },
                )
            result["final_solution"] = self.full_rhs.duplicate()
            result["final_solution"].array[:] = self.last_evaluation["storage_solution"]
        finally:
            y.destroy()
        post_ksp_end_ns = time.perf_counter_ns()
        result["outer_adapter_return_tail"] = {
            "scope": (
                "from_retained_fgmres_return_through_outer_adapter_return"
            ),
            "start_monotonic_ns": int(post_ksp_started_ns),
            "end_monotonic_ns": int(post_ksp_end_ns),
            "elapsed_seconds": float(
                (post_ksp_end_ns - post_ksp_started_ns) / 1.0e9
            ),
            "includes": [
                "condensation cache validation",
                "retained final packet save",
                "optional complete field packet save",
            ],
            "is_pure_ksp": False,
        }
        return result

    def facts(self):
        if self._released_after_final_residual and self._released_facts is not None:
            return dict(self._released_facts)
        return {"identity": self.identity, "setup_checks": self.checks, "cache": self.cache,
                "counts": dict(self.count), "timings": dict(self.time),
                "role_counts": {
                    role: dict(counts) for role, counts in self.role_counts.items()
                },
                "role_timings": dict(self.role_timings),
                "actual_first_arnoldi": dict(self.actual_first_arnoldi),
                "core_counts": dict(self.action.audit),
                "retained_checkpoints": self.retained_checkpoints,
                "residual_packets": self.residual_packets,
                "orthogonalization_seconds": None,
                "orthogonalization_timing_status": "not separately instrumented; included in KSP total",
                "factor_lifetime": "p4 LU and p6 caches retained through final native field evaluation"}

    def release_after_final_residual(self):
        """Release p6-owned data after the saved field and pre-release A6 gate."""

        if self._released_after_final_residual:
            return {"status": "ALREADY_RELEASED"}
        if not self._final_packet_saved:
            raise RuntimeError(
                "cannot release p6 cache before the complete field packet is saved"
            )
        snapshot = self.facts()
        self.runtime.marker(
            "v20_p6_release_started",
            {
                "field_packet_saved": True,
                "pre_release_A6_checked": True,
                "identity_cache_mode": self.identity_cache_mode,
            },
        )
        self.destroy()
        self._released_after_final_residual = True
        snapshot["factor_lifetime"] = "p6 caches released after pre-release A6 and before official output"
        snapshot["released_after_final_residual"] = True
        snapshot["release_owner_refs_cleared"] = True
        self._released_facts = snapshot
        inventory_label = f"{self.evidence_prefix}_p6_local_caches"
        self.runtime.marker(
            "v20_p6_release_complete",
            {
                "released_after_final_residual": True,
                "owner_refs_cleared": True,
                "workspace_labels_released": [
                    f"{self.evidence_prefix}_p6_setup",
                    f"{self.evidence_prefix}_p6_full_scratch",
                ],
                "inventory_label_released": inventory_label,
            },
        )
        return {
            "status": "RELEASED",
            "released_after_final_residual": True,
            "owner_refs_cleared": True,
        }

    def destroy(self):
        self.last_evaluation = None
        for value in (self.rhs, self.full_source, self.full_target):
            if value is not None:
                value.destroy()
        if self.action is not None:
            self.action.destroy()
        if self.condensed is not None:
            self.condensed.destroy()
        self.action = self.condensed = self.rhs = self.full_source = self.full_target = None
        self.bridge = None
        # These are owner/closure references, not external resources.  Clear
        # them after the numerical objects have been destroyed so a V20
        # weak-reference probe can distinguish a real release from a ledger
        # decrement that leaves the p6 graph reachable.
        self.bal_h = None
        self.common = None
        self.resolved = None
        self.pc_counts = None
        self.compiled_form = None
        self.full_rhs = None
        self.runtime.release_workspace(f"{self.evidence_prefix}_p6_setup")
        self.runtime.release_workspace(f"{self.evidence_prefix}_p6_full_scratch")
        self.runtime.release_inventory(f"{self.evidence_prefix}_p6_local_caches")


def build_retained_outer_adapter(*args, **kwargs):
    adapter = RetainedOuterAdapter(*args, **kwargs)
    try:
        adapter.build()
        return adapter
    except BaseException:
        adapter.destroy()
        raise


def _compiled_form_identity(compiled_form):
    """Return small, JSON-safe identity facts for one prepared DOLFINx form."""

    module = getattr(compiled_form, "module", None)
    if isinstance(module, (tuple, list)):
        module_files = [str(getattr(item, "__file__", "")) for item in module]
    else:
        module_files = [str(getattr(module, "__file__", ""))]
    module_files = [value for value in module_files if value]
    form_rank = getattr(compiled_form, "rank", None)
    try:
        form_rank = None if form_rank is None else int(form_rank)
    except (TypeError, ValueError):
        form_rank = str(form_rank)
    return {
        "dtype": str(getattr(compiled_form, "dtype", "unknown")),
        "module_file": module_files[0] if module_files else None,
        "module_files": module_files,
        "module_count": len(module_files),
        "rank": form_rank,
        "cache_state": "observed_from_ffcx_return_code",
    }


_V20_EXCLUDED_FFCX_MODULE = (
    "libffcx_forms_9c081a2454e80304289733853e6aa2b2d94badd9"
)


def _v20_form_cache(runtime, *, cache_policy="v20_exclude_old_family"):
    """Create the run-owned FFCx cache under an explicit profile policy.

    The historical V20 default keeps its excluded-module contract.  V21 opts
    into the same run-owned hard-link cache while reusing every qualified
    module; it records actual compiler hit/miss observations under the same
    watchdog root instead of manufacturing a cold-miss comparison.
    """

    if cache_policy not in {
        "v20_exclude_old_family",
        "v21_reuse_all_qualified",
    }:
        raise ValueError(f"unsupported prepared-form cache policy: {cache_policy}")

    from dolfinx import jit

    qualified_source = os.environ.get("PHYSICAL_QUALIFIED_JIT_CACHE_SOURCE")
    if qualified_source:
        source = Path(qualified_source).expanduser().resolve()
        if not source.is_dir():
            raise FileNotFoundError(
                f"qualified JIT cache source does not exist: {source}"
            )
        source_binding = "explicit_qualified_formal_root"
    else:
        source = Path(jit.get_options()["cache_dir"]).expanduser().resolve()
        source_binding = "activation_jit_cache"
    target = (Path(runtime.directory) / "v20_jit_cache" / "fenics").resolve()
    target.mkdir(parents=True, exist_ok=True)
    copied = hardlinked = copied_bytes = excluded = excluded_bytes = 0
    if source.is_dir() and source != target:
        for source_path in source.rglob("*"):
            if not source_path.is_file():
                continue
            relative = source_path.relative_to(source)
            if (
                cache_policy == "v20_exclude_old_family"
                and source_path.name.startswith(_V20_EXCLUDED_FFCX_MODULE)
            ):
                excluded += 1
                excluded_bytes += int(source_path.stat().st_size)
                continue
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                continue
            try:
                os.link(source_path, destination)
                hardlinked += 1
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                # A run directory can be on a different filesystem.  Keep the
                # same exact cache population contract in that case, while
                # making the fallback explicit in the evidence.
                import shutil

                shutil.copy2(source_path, destination)
                copied += 1
            copied_bytes += int(source_path.stat().st_size)
    for existing in target.rglob("*"):
        if (
            cache_policy == "v20_exclude_old_family"
            and existing.is_file()
            and existing.name.startswith(_V20_EXCLUDED_FFCX_MODULE)
        ):
            raise RuntimeError(
                "V20 dedicated cache contains the excluded V19 target module family"
            )
    return target, {
        "cache_policy": cache_policy,
        "source_cache_dir": str(source),
        "source_cache_binding": source_binding,
        "qualified_source_origin": os.environ.get(
            "PHYSICAL_QUALIFIED_JIT_CACHE_ORIGIN"
        ),
        "qualified_expected_compiler_event_count": (
            int(os.environ["PHYSICAL_QUALIFIED_JIT_EXPECTED_COMPILER_EVENTS"])
            if os.environ.get("PHYSICAL_QUALIFIED_JIT_EXPECTED_COMPILER_EVENTS")
            else None
        ),
        "formal_cache_dir": str(target),
        "same_compiler_options": ["-O2", "-g0"],
        "hardlinked_eligible_files": hardlinked,
        "copied_eligible_files": copied,
        "eligible_bytes": copied_bytes,
        "excluded_module_family": (
            _V20_EXCLUDED_FFCX_MODULE
            if cache_policy == "v20_exclude_old_family"
            else None
        ),
        "excluded_file_count": excluded,
        "excluded_bytes": excluded_bytes,
        "source_cache_untouched": True,
    }


def _module_files(module):
    if isinstance(module, (tuple, list)):
        return [str(getattr(item, "__file__", "")) for item in module]
    return [str(getattr(module, "__file__", ""))]


def _module_file_facts(paths, hash_cache):
    facts = []
    for raw_path in paths:
        path = Path(raw_path) if raw_path else None
        if path is None or not path.is_file():
            facts.append({"path": raw_path, "size": None, "sha256": None})
            continue
        key = str(path)
        digest = hash_cache.get(key)
        if digest is None:
            hasher = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1 << 20), b""):
                    hasher.update(block)
            digest = hasher.hexdigest()
            hash_cache[key] = digest
        facts.append(
            {
                "path": key,
                "size": int(path.stat().st_size),
                "sha256": digest,
            }
        )
    return facts


def _small_option_facts(value):
    if not isinstance(value, dict):
        return None
    result = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            result[str(key)] = item
        elif isinstance(item, (tuple, list)):
            result[str(key)] = [str(entry) for entry in item]
        else:
            result[str(key)] = str(item)
    return result


def _v20_observed_code(returned_code):
    if not isinstance(returned_code, tuple) or len(returned_code) != 2:
        raise RuntimeError("dolfinx.jit.ffcx_jit returned an invalid code tuple")
    return [None if item is None else "<non_none>" for item in returned_code]


def prepare_dual_condensed_forms(
    runtime,
    common,
    *,
    coarse_degree: int | None = None,
    cache_policy="v20_exclude_old_family",
):
    """Compile the p6 and requested coarse complete cell forms before factors.

    The returned compiled objects are intentionally borrowed by the caller for
    one setup root and are not inserted into the ordinary V19 path.
    """

    from dolfinx import fem, jit
    import ufl

    actual_coarse_degree = int(common.get("coarse_degree", 4))
    if coarse_degree is None:
        coarse_degree = actual_coarse_degree
    coarse_degree = int(coarse_degree)
    if coarse_degree != actual_coarse_degree:
        raise ValueError("prepared-form coarse degree disagrees with common")
    if coarse_degree not in (2, 3, 4):
        raise ValueError("prepared-form coarse degree must be 2, 3, or 4")
    coarse = common.get("coarse")
    if coarse is None:
        if coarse_degree != 4 or "p4" not in common:
            raise KeyError("common is missing the requested coarse action")
        coarse = common["p4"]

    cache_dir, cache_facts = _v20_form_cache(runtime, cache_policy=cache_policy)
    jit_options = {
        "cache_dir": str(cache_dir),
        "cffi_extra_compile_args": ["-O2", "-g0"],
        "cffi_debug": False,
    }
    compiler_events = []
    original_ffcx_jit = jit.ffcx_jit
    module_hash_cache = {}

    def observed_ffcx_jit(*args, **kwargs):
        started_ns = time.time_ns()
        started = perf_counter()
        compiled_object, module, returned_code = original_ffcx_jit(*args, **kwargs)
        elapsed_seconds = perf_counter() - started
        finished_ns = time.time_ns()
        code = _v20_observed_code(returned_code)
        module_files = _module_files(module)
        call = {
            "index": len(compiler_events),
            "module_files": module_files,
            "module_file_facts": _module_file_facts(module_files, module_hash_cache),
            "code": code,
            "cache_hit": code == [None, None],
            "started_timestamp_ns": started_ns,
            "finished_timestamp_ns": finished_ns,
            "elapsed_seconds": elapsed_seconds,
            "form_compiler_options": _small_option_facts(
                kwargs.get("form_compiler_options")
                if "form_compiler_options" in kwargs
                else (args[1] if len(args) > 1 else None)
            ),
            "jit_options": _small_option_facts(kwargs.get("jit_options")),
        }
        compiler_events.append(
            call
        )
        return compiled_object, module, returned_code

    jit.ffcx_jit = observed_ffcx_jit
    prepared = {}
    form_metadata = {}
    official_roles = []

    def compile_form(role, form):
        before = len(compiler_events)
        compiled = fem.form(form, jit_options=dict(jit_options))
        events = compiler_events[before:]
        for event in events:
            event["role"] = role
        form_metadata[role] = {
            "form": _compiled_form_identity(compiled),
            "compiler_events": list(events),
            "cache_hit": bool(events and all(event["cache_hit"] for event in events)),
        }
        return compiled

    def compile_expression(role, expression, points):
        before = len(compiler_events)
        compiled = fem.Expression(
            expression,
            points,
            jit_options=dict(jit_options),
        )
        events = compiler_events[before:]
        for event in events:
            event["role"] = role
        official_roles.append(
            {
                "role": role,
                "kind": "Expression",
                "compiler_events": list(events),
                "cache_hit": bool(events and all(event["cache_hit"] for event in events)),
            }
        )
        return compiled

    try:
        runtime.marker(
            "v20_form_preparation_started",
            {
                "roles": [
                    "p6_condensation",
                    f"q{coarse_degree}_condensation",
                ],
                "coarse_degree": coarse_degree,
                "evaluation_forms": "official postprocess kernels are compiled below",
                "jit_options": jit_options,
                "cache": cache_facts,
            },
        )
        prepared["p6_condensation"] = compile_form(
            "p6_condensation", common["fine"]["volume_action"].bilinear_form
        )
        coarse_role = (
            "p4_condensation" if coarse_degree == 4 else f"q{coarse_degree}_condensation"
        )
        coarse_form = compile_form(
            coarse_role, coarse["volume_action"].bilinear_form
        )
        prepared["coarse_condensation"] = coarse_form
        # Compatibility for the existing V20 holder contract.  This is the
        # same compiled object, never a second degree-4 compilation.
        prepared["p4_condensation"] = coarse_form

        # These are the actual rank-zero/Expression kernels used by the
        # official 3D output path.  Compiling the native rank-one action or
        # the lossless diagnostic metric is not a substitute for them.
        levels = common["levels"]
        cfg = common["cfg"]
        field = fem.Function(
            levels["floquets"][6].mpc.function_space,
            name="v20_postprocess_probe_field",
        )
        mesh_data = levels["mesh_data"]
        dx = ufl.Measure("dx", domain=mesh_data.mesh, subdomain_data=mesh_data.cell_tags)
        d_physical = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))
        for component in range(3):
            role = f"postprocess_component_l2_{component}"
            compile_form(role, ufl.inner(field[component], field[component]) * d_physical)
            official_roles.append({"role": role, "kind": "Form", **form_metadata[role]})
        for tag_name, tag in (("grating", cfg.tags.grating), ("substrate", cfg.tags.substrate)):
            volume_role = f"rta_region_volume_{tag_name}"
            compile_form(volume_role, ufl.as_ufl(1.0) * dx(tag))
            official_roles.append({"role": volume_role, "kind": "Form", **form_metadata[volume_role]})
            absorption_role = f"rta_region_absorption_{tag_name}"
            density_scale = 0.5 * cfg.k0 * float(
                complex(cfg.eps_grating if tag_name == "grating" else cfg.eps_substrate).imag
            )
            compile_form(
                absorption_role,
                density_scale * ufl.real(ufl.inner(field, field)) * dx(tag),
            )
            official_roles.append({"role": absorption_role, "kind": "Form", **form_metadata[absorption_role]})

        from src.postprocessing.postprocess_3d import _interpolation_points as postprocess_points
        from src.postprocessing.diffraction_3d import _interpolation_points as diffraction_points

        postprocess_space = fem.functionspace(
            mesh_data.mesh, ("DG", cfg.visualization_degree, (3,))
        )
        diffraction_space = fem.functionspace(
            mesh_data.mesh, ("DG", max(int(cfg.visualization_degree), 1), (3,))
        )
        postprocess_h = (cfg.magnetic_field_scale_A_per_m / (1j * cfg.k0 * cfg.mu_r)) * ufl.curl(field)
        diffraction_h = (1.0 / (1j * cfg.k0 * cfg.mu_r)) * ufl.curl(field)
        for role, expression, points in (
            ("postprocess_E_to_H_expression", postprocess_h, postprocess_points(postprocess_space)),
            ("diffraction_E_to_H_expression", diffraction_h, diffraction_points(diffraction_space)),
        ):
            expression_object = compile_expression(role, expression, points)
            del expression_object
        del postprocess_space, diffraction_space, field
        gc.collect()
    finally:
        jit.ffcx_jit = original_ffcx_jit

    facts = {
        "schema": "task039extra.v20.prepared-forms.v2",
        "cache_policy": cache_policy,
        "same_watchdog_root": True,
        "pre_factor": True,
        "jit_options": jit_options,
        "cache": cache_facts,
        "coarse_degree": coarse_degree,
        "compatibility_aliases": {
            "p4_condensation": "coarse_condensation"
        },
        "roles": {key: _compiled_form_identity(value) for key, value in prepared.items()},
        "compiler_events": list(compiler_events),
        "compiler_event_count": len(compiler_events),
        "official_evaluation_roles": official_roles,
        "official_evaluation_role_count": len(official_roles),
        "p6_module_reused_by_adapter": True,
        "p4_module_reused_by_stack": True,
        "identity_cache_mode": "shared_read_only_per_interior_shape",
        "cache_claim": "derived from ffcx_jit return code [None, None] and compiler module paths",
    }
    runtime.marker("v20_form_preparation_complete", facts)
    return prepared, facts
