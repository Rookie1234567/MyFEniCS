"""V19 setup/evidence adapter; numerical actions remain in src.solvers."""

import hashlib
import json
from time import perf_counter

import numpy as np

from .physical_p4_schur_v14 import _save_packet


BASELINE_RHS_SHA256 = "e8ece14d273d8bcdec672f2e29ac8c62971bb0d0fe4af7cc63e741df21934686"


def _array_identity(value):
    array = np.ascontiguousarray(value)
    return {"shape": list(array.shape), "dtype": str(array.dtype),
            "sha256": hashlib.sha256(memoryview(array).cast("B") if array.size else b"").hexdigest()}


def _cache_identity(action):
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
    return {"arrays": identities, "array_content_sha256": digest,
            "unique_numpy_bytes": sum(unique.values()), "components": groups,
            "scatter_vectors_bytes": 0,
            "scope": "resident numerical payload; Python/PETSc allocator overhead measured by full tree RSS"}


class RetainedOuterAdapter:
    def __init__(self, runtime, common, resolved, full_rhs, apply_pc, *, p4_identity_sha256, pc_counts):
        self.runtime, self.common, self.resolved = runtime, common, resolved
        self.full_rhs, self.bal_h = full_rhs, apply_pc
        self.p4_identity_sha256 = p4_identity_sha256
        self.pc_counts = pc_counts
        self.action = self.rhs = self.condensed = None
        self.full_source = self.full_target = None
        self.last_evaluation = None
        self.identity = {}
        self.checks = {}
        self.residual_packets = []
        self.retained_checkpoints = {}
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

        def allocation_gate(name, facts):
            if name != "cell_tensor_working_set":
                raise ValueError("V19 p6 unexpectedly requested global matrix storage")
            amount = int(facts["retained_numeric_bytes_upper"])
            runtime.check_inventory_projected("v19_p6_local_caches", amount)
            runtime.check_projected("v19_p6_local_caches", amount, workspace_bytes=int(facts["workspace_bytes"]))
            runtime.reserve_workspace("v19_p6_setup", int(facts["workspace_bytes"]))

        runtime.marker("v19_p6_local_setup_started", {"global_matrix": False})
        self.condensed = build_unconstrained_assembly_time_condensation(
            fem.form(self.common["fine"]["volume_action"].bilinear_form),
            levels["spaces"][6], levels["mesh_data"].cell_tags, mpc=levels["floquets"][6].mpc,
            appended_global_rows=len(self.common["fine"]["dtn_action"].carrier.entries),
            sum_duplicate_cell_integrals=True, strict_local_checks=True,
            materialize_global_matrix=False, retain_local_schur_for_matrix_free=True,
            allocation_gate=allocation_gate,
        )
        runtime.release_workspace("v19_p6_setup")
        runtime.reserve_workspace("v19_p6_setup", 128 << 20)
        self.action = build_p6_cell_condensed_action_from_carrier(
            self.condensed, self.common["fine"]["dtn_action"].carrier,
        )
        cache = _cache_identity(self.action)
        runtime.reserve_inventory("v19_p6_local_caches", {
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
        self._packet("x1_p6_cache_identity", {"identity": self.identity, "cache": cache})
        self.cache = {k: v for k, v in cache.items() if k != "arrays"}
        runtime.release_workspace("v19_p6_setup")
        # Simultaneous full scratch, residual packet arrays, bridge outputs,
        # and the fixed three-vector setup fixture; the Krylov pool is separate.
        scratch_bytes = 24 * int(self.full_rhs.getLocalSize()) * 16 + 10 * self.action.reduced_size * 16
        runtime.reserve_workspace("v19_p6_full_scratch", scratch_bytes)
        self.full_source, self.full_target = self.full_rhs.duplicate(), self.full_rhs.duplicate()
        self.rhs = self.action.create_reduced_rhs_vector()
        self.rhs.array[:] = self.action.reduce_rhs(self.full_rhs, rhs_is_mpc_dual=True)
        self.bridge = P6RetainedBALHBridge(self.action, self._bal_h_array)
        self.time["setup_seconds"] = perf_counter() - started
        runtime.marker("v19_p6_local_setup_complete", {"identity": self.identity, "cache": self.cache})

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
        facts["resource"] = dict(self.runtime.sample("v19_native_residual"))
        return facts

    def setup_checks(self):
        started = perf_counter()
        system = self.condensed
        actual = (system.full_rows, system.active_rows, system.interior_rows, system.appended_rows)
        expected = (173802, 51192, 113400, 80)
        if actual != expected:
            raise ValueError(f"derived p6 topology differs: {actual} != {expected}")
        if _array_identity(self.full_rhs.array_r)["sha256"] != BASELINE_RHS_SHA256:
            raise ValueError("new original physical RHS differs from accepted V18")
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
                           "physical_rhs_sha256": BASELINE_RHS_SHA256,
                           "space_counts": list(actual), "setup_pc_calls": 1,
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
            cache_after = _cache_identity(self.action)
            if cache_after["array_content_sha256"] != self.cache["array_content_sha256"]:
                raise ValueError("p6 condensation cache content changed across outer calls")
            if cache_after["unique_numpy_bytes"] != self.cache["unique_numpy_bytes"]:
                raise ValueError("p6 condensation cache payload grew across calls")
            result["p6_cache_after"] = {k: v for k, v in cache_after.items() if k != "arrays"}
            result["actual_pc_counts_including_one_setup_call"] = self.pc_counts()
            self._packet("x2_retained_final", {"identity": self.identity, "retained_y": y.array_r.copy(),
                         "physical_rhs": self.full_rhs.array_r.copy(), "facts": result["final_evaluation"],
                         "residuals": self.last_evaluation})
            result["final_solution"] = self.full_rhs.duplicate()
            result["final_solution"].array[:] = self.last_evaluation["storage_solution"]
        finally:
            y.destroy()
        return result

    def facts(self):
        return {"identity": self.identity, "setup_checks": self.checks, "cache": self.cache,
                "counts": dict(self.count), "timings": dict(self.time),
                "core_counts": dict(self.action.audit),
                "retained_checkpoints": self.retained_checkpoints,
                "residual_packets": self.residual_packets,
                "orthogonalization_seconds": None,
                "orthogonalization_timing_status": "not separately instrumented; included in KSP total",
                "factor_lifetime": "p4 LU and p6 caches retained through final native field evaluation"}

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
        self.runtime.release_workspace("v19_p6_setup")
        self.runtime.release_workspace("v19_p6_full_scratch")
        self.runtime.release_inventory("v19_p6_local_caches")


def build_retained_outer_adapter(*args, **kwargs):
    adapter = RetainedOuterAdapter(*args, **kwargs)
    try:
        adapter.build()
        return adapter
    except BaseException:
        adapter.destroy()
        raise
