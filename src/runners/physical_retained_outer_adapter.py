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
        self.time = {"setup_seconds": 0.0, "schur_action_seconds": 0.0,
                     "bridge_seconds": 0.0, "bal_h_seconds": 0.0,
                     "native_action_seconds": 0.0, "recovery_evaluation_seconds": 0.0,
                     "packet_seconds": 0.0}
        self.count = {"schur_action": 0, "bridge": 0, "native_action": 0}

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
        self.count["native_action"] += 1
        self.time["native_action_seconds"] += perf_counter() - started
        return self.full_target.array_r.copy()

    def _apply(self, source):
        started = perf_counter()
        result = self.action.apply(source)
        self.count["schur_action"] += 1
        self.time["schur_action_seconds"] += perf_counter() - started
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
        self.count["bridge"] += 1
        self.time["bridge_seconds"] += perf_counter() - started
        return result

    def _evaluate(self, source, _schur_residual):
        started = perf_counter()
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

    def setup_checks(self):
        started = perf_counter()
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
            pc_delta = {key: value - pc_before[key] for key, value in pc_after.items()}
            self._packet("x1_pc_count_check", {
                "before": pc_before, "after": pc_after, "delta": pc_delta,
                "input": inputs.array_r.copy(), "output": output.array_r.copy(),
                "source_sha": self.runtime.source_sha,
            })
            if pc_delta != {"bal_h": 1, "p4_mat_solve": 2, "h6": 1}:
                raise ValueError(f"X1 bridge violated fixed action count: {pc_delta}")
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
                           "setup_seconds": perf_counter() - started,
                           "single_pc_reduction_gate": False}
            self._packet("x1_setup_checks", self.checks)
            self.checks = {k: v for k, v in self.checks.items() if not isinstance(v, np.ndarray)}
        finally:
            if output is not None:
                output.destroy()
            inputs.destroy()
            self.last_evaluation = None

    def solve(self, *, checkpoint, append, seconds, resource_sample, stop_requested):
        from src.solvers.physical_retained_fgmres import run_retained_fgmres

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

        result = run_retained_fgmres(
            self.rhs, self._apply, self._pc, evaluate=self._evaluate,
            checkpoint=full_checkpoint, save_retained=save_retained, append=save_row, seconds=seconds,
            resource_sample=resource_sample, stop_requested=stop_requested,
        )
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
        return result

    def facts(self):
        if self._released_after_final_residual and self._released_facts is not None:
            return dict(self._released_facts)
        return {"identity": self.identity, "setup_checks": self.checks, "cache": self.cache,
                "counts": dict(self.count), "timings": dict(self.time),
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
    runtime, common, *, cache_policy="v20_exclude_old_family"
):
    """Compile the p6 and p4 complete cell forms before factor construction.

    The returned compiled objects are intentionally borrowed by the caller for
    one setup root and are not inserted into the ordinary V19 path.
    """

    from dolfinx import fem, jit
    import ufl

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
                "roles": ["p6_condensation", "p4_condensation"],
                "evaluation_forms": "official postprocess kernels are compiled below",
                "jit_options": jit_options,
                "cache": cache_facts,
            },
        )
        for role, action in (
            ("p6_condensation", common["fine"]["volume_action"]),
            ("p4_condensation", common["p4"]["volume_action"]),
        ):
            prepared[role] = compile_form(role, action.bilinear_form)

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
