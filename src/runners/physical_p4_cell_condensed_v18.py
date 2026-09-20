"""Review V18 cell-condensed p4 stack and its Full3D dispatch adapter.

The exact route owns one assembly-time condensed matrix and one global factor.
Its ``fint`` object implements the same ``apply_with_facts`` contract consumed
by :class:`InterfaceBalancedCoupling`; H6, transfer, and the p6 outer solve
remain in the established V14 helper.  The worker keeps the stage boundaries
explicit: U2/U3 are p4 controls, while U4/U5 reuse the established p6 BAL_H
driver with only its p4 ``fint`` implementation replaced.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import time
from typing import Any, Mapping

import numpy as np

from src.io.physical_intermediate_profile import (
    CELL_CONDENSED_BLR_PROFILE,
    CELL_CONDENSED_EXACT_PROFILE,
    profile_facts,
)


_FORMAL_STAGES = {
    "U2_EXACT_CONTROL",
    "U3_BLR_CONTROL",
    "U4_ORIGINAL",
    "U4_EXACT_FALLBACK",
    "U5_NOTCH",
    "U6_FINALIZE",
}
_RHS_STEMS = (
    "A2R160_BAL_H_p4_01",
    "A2R160_BAL_H_p4_02",
    "LIGHT448_BAL_H_p4_09",
)


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    """Convert worker facts without hiding non-JSON values as strings."""

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        array = np.ascontiguousarray(value)
        return {
            "shape": list(array.shape),
            "dtype": str(array.dtype),
            "sha256": hashlib.sha256(array.tobytes()).hexdigest(),
        }
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _identity_sha(array: Any) -> str:
    data = np.ascontiguousarray(np.asarray(array))
    return hashlib.sha256(data.tobytes()).hexdigest()


def _runtime_marker(runtime: Any, name: str, facts: Mapping[str, Any]) -> None:
    marker = getattr(runtime, "marker", None)
    if callable(marker):
        marker(name, dict(facts))


def _runtime_sample(runtime: Any, label: str) -> Mapping[str, Any]:
    sample = getattr(runtime, "sample", None)
    if callable(sample):
        return dict(sample(label))
    return {"status": "not_sampled", "label": label}


class CellCondensedFintAdapter:
    """Adapt the exact V18 inverse to the existing BAL_H coarse callback."""

    def __init__(self, inverse: Any) -> None:
        self.inverse = inverse
        # ``apply_count`` is deliberately the number of physical F4 adapter
        # calls, including repair RHS calls.  A logical BAL_H coarse call is
        # tracked separately by ``logical_apply_count``.
        self.apply_count = 0
        self.logical_apply_attempt_count = 0
        self.logical_apply_count = 0

    def begin_logical_apply(self) -> None:
        self.logical_apply_attempt_count += 1

    def complete_logical_apply(self) -> None:
        self.logical_apply_count += 1

    def apply_with_facts(self, rhs: Any, *, port_rhs: Any | None = None):
        if port_rhs is not None:
            values = np.asarray(port_rhs, dtype=np.complex128)
            if values.size and np.any(values != 0.0):
                raise ValueError(
                    "V18 exact adapter does not accept an auxiliary port RHS"
                )
        correction = self.inverse.apply(rhs)
        self.apply_count += 1
        facts = dict(self.inverse.last_audit)
        facts.update(
            {
                "adapter_schema": "task039extra.v18.cell-condensed-fint.v1",
                "apply_count": int(self.apply_count),
                "apply_count_semantics": "physical_F4_calls_including_repairs",
                "logical_apply_count": int(self.logical_apply_count),
                "logical_apply_attempt_count": int(
                    self.logical_apply_attempt_count
                ),
                "factor_solve_count": int(self.inverse.solve_count),
                "factor_solve_call_delta": int(
                    facts.get("factor_solve_call_delta") or 0
                ),
                "matrix_identity": dict(self.inverse.matrix_identity),
                "port_rhs_policy": "zero_only",
                "port_solution_norm": float(
                    np.linalg.norm(self.inverse.last_port_solution)
                ),
            }
        )
        return correction, facts

    @property
    def last_port_solution(self):
        return self.inverse.last_port_solution

    @last_port_solution.setter
    def last_port_solution(self, value):
        self.inverse.last_port_solution = np.asarray(
            value, dtype=np.complex128
        ).copy()

    def destroy(self) -> None:
        self.inverse.destroy()


def _factor_factory_for_backend(backend: str):
    from src.solvers.fullspace_v17_p3_oracle import MumpsBLRFactor, _MumpsFactor

    backend = str(backend)
    if backend == "exact":
        def factory(matrix: Any) -> Any:
            factor = _MumpsFactor(matrix)
            # These controls are set before _prepare_factor invokes symbolic.
            factor.set_icntl(35, 0)
            factor.set_icntl(10, 0)
            for index, value in ((2, 0), (3, 6), (4, 2)):
                factor.set_icntl(index, value)
            return factor

        return factory
    if backend == "blr":
        def factory(matrix: Any) -> Any:
            factor = MumpsBLRFactor(
                matrix,
                profile="physical_p4_cell_condensed_blr_v18",
                threshold=1.0e-5,
                enable_coverage_statistics=True,
            )
            factor.configure_blr()
            return factor

        return factory
    raise ValueError(f"unsupported V18 backend {backend!r}")


def _operator_identity(
    common: Mapping[str, Any],
    resolved_payload: Mapping[str, Any],
    condensed: Any,
    matrix_identity: Mapping[str, Any],
    *,
    stage: str,
) -> tuple[dict[str, Any], str]:
    from src.runners.physical_macro_controls import _mapping_identity_sha256
    from src.solvers.condensed_fine_reference import native_map_arrays

    provenance = resolved_payload.get("provenance", {})
    if not isinstance(provenance, Mapping):
        provenance = {}
    input_sha = str(provenance.get("input_sha256", resolved_payload.get("input_sha256", "")))
    physical_sha = str(
        provenance.get(
            "physical_model_sha256",
            resolved_payload.get("physical_model_sha256", ""),
        )
    )
    active_trace = set(
        map(int, condensed.trace_constraints.owned_active_original_dofs)
    )
    p4_map = native_map_arrays(
        common["levels"]["spaces"][4], common["levels"]["floquets"][4]
    )
    p6_map = native_map_arrays(
        common["levels"]["spaces"][6], common["levels"]["floquets"][6]
    )
    identity = {
        "schema": "task039extra.v18.cell-condensed-operator-identity.v1",
        "stage": str(stage),
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "ordered_mode_sha256": str(common["fine"]["mode_sha256"]),
        "p4_native_map_sha256": _mapping_identity_sha256(p4_map),
        "p6_native_map_sha256": _mapping_identity_sha256(p6_map),
        "p4_storage_rows": int(common["p4"]["dtn_action"].carrier.global_rows),
        "p6_storage_rows": int(common["fine"]["dtn_action"].carrier.global_rows),
        "condensed_rows": int(condensed.matrix.getSize()[0]),
        "condensed_matrix_identity": dict(matrix_identity),
        "partition": {
            "storage_size": int(condensed.full_rows),
            "active_rows": int(condensed.active_rows),
            "appended_rows": int(condensed.appended_rows),
            "active_trace_sha256": _identity_sha(
                condensed.trace_constraints.owned_active_original_dofs
            ),
            "slave_rows_sha256": _identity_sha(
                np.asarray(
                    [
                        value
                        for value in condensed.owned_trace_original_dofs
                        if int(value) not in active_trace
                    ],
                    dtype=np.int64,
                )
            ),
        },
        "quadrature": common["quadrature"],
        "reference_used_for_operator_or_initial_guess": False,
        "initial_guess": "zero",
    }
    return identity, _sha256_json(identity)


@contextmanager
def cell_condensed_stack(
    runtime: Any,
    common: Mapping[str, Any],
    resolved_payload: Mapping[str, Any],
    *,
    stage: str,
    backend: str = "exact",
    compiled_form: Any | None = None,
    compiled_form_holder: dict[str, Any] | None = None,
    matrix_lifecycle_policy: str = "LEGACY_RETAIN_THROUGH_POSTPROCESS",
    factor_memory_request_builder=None,
    factor_numeric_observer=None,
    factor_post_numeric_gate=None,
    capacity_metadata_callback=None,
):
    """Build and own the V18 condensed matrix/factor for one stage.

    The combined UFL volume form is compiled once and passed to the
    assembly-time builder.  Port rows are inserted directly into that matrix;
    no old full p4 volume matrix, macro-block stack, or dense global Schur is
    created.
    """

    from dolfinx import fem
    from src.solvers.hcurl_assembly_time_condensation import (
        build_unconstrained_assembly_time_condensation,
    )
    from src.solvers.p4_cell_condensed_inverse import (
        P4CellCondensedInverse,
        assemble_condensed_ports,
        petsc_csr_content_identity,
    )
    from src.solvers.physical_interface_schur import _prepare_factor

    if int(common["levels"]["mesh"].comm.size) != 1:
        raise NotImplementedError("V18 cell-condensed stack is qualified for MPI1")
    p4 = common["p4"]
    levels = common["levels"]
    volume_action = p4["volume_action"]
    carrier = p4["dtn_action"].carrier
    volume_form = volume_action.bilinear_form
    owns_compiled_form = compiled_form is None
    condensed = None
    factor = None
    inverse = None
    adapter = None
    stack_result = None
    port_terms = {}
    mapping_arrays = []
    matrix_inventory_label = f"v18_{backend}_condensed_matrix"
    factor_inventory_label = f"v18_{backend}_condensed_global"
    assembly_workspace = f"v18_{backend}_assembly"
    setup_started = time.perf_counter()
    allocation_audit = []
    pending_matrix_bytes = 0

    def allocation_gate(name, facts):
        nonlocal pending_matrix_bytes
        allocation_audit.append({"name": name, **dict(facts)})
        if name == "condensed_matrix":
            amount = int(facts["matrix_payload_bytes"])
            pending_matrix_bytes = amount
            runtime.check_inventory_projected(matrix_inventory_label, amount)
            runtime.check_projected(matrix_inventory_label, amount,
                                    workspace_bytes=int(facts.get("workspace_bytes", 0)))
        elif name == "cell_tensor_working_set":
            amount = int(facts["retained_numeric_bytes_upper"])
            runtime.check_inventory_projected("v18_cell_caches", amount + pending_matrix_bytes)
            runtime.check_projected("v18_cell_caches", amount,
                                    workspace_bytes=int(facts["workspace_bytes"]))
            runtime.reserve_workspace(assembly_workspace, int(facts["workspace_bytes"]))
        else:
            raise ValueError(f"unknown condensation allocation boundary {name}")
    try:
        runtime.set_phase("assembly")
        _runtime_marker(runtime, "v18_cell_condensed_assembly_started", {"stage": stage})
        if compiled_form is None:
            compiled_form = fem.form(volume_form)
        condensed = build_unconstrained_assembly_time_condensation(
            compiled_form,
            levels["spaces"][4],
            levels["mesh_data"].cell_tags,
            mpc=levels["floquets"][4].mpc,
            appended_global_rows=len(carrier.entries),
            appended_support_owned_cell_groups=(
                np.arange(
                    int(levels["mesh"].topology.index_map(3).size_local),
                    dtype=np.int32,
                ),
            ),
            appended_support_group_by_row=tuple(0 for _ in carrier.entries),
            dense_appended_block=True,
            sum_duplicate_cell_integrals=True,
            strict_local_checks=True,
            defer_final_assembly=True,
            allocation_gate=allocation_gate,
        )
        # The V20 lifecycle explicitly releases the complete compiled form
        # after its setup consumer has built the owned kernels.  Preserve the
        # historical V18/V19 lifetime when neither the new policy nor an
        # explicit holder was supplied.
        if (
            matrix_lifecycle_policy == "MATRIX_RETAINED_BACKEND_DEPENDENCY"
            or compiled_form_holder is not None
        ):
            compiled_form = None
            if compiled_form_holder is not None:
                compiled_form_holder["form"] = None
        runtime.release_workspace(assembly_workspace)
        # Bound local carrier/recovery construction and map/hash temporaries.
        runtime.reserve_workspace(assembly_workspace, 64 << 20)
        port_terms = assemble_condensed_ports(condensed, carrier)
        matrix_before = petsc_csr_content_identity(condensed.matrix)
        matrix_info = condensed.matrix.getInfo()
        from src.runners.physical_p4_schur_v14 import (
            _factor_gates,
            _sparse_payload_bytes,
        )
        retained_cache = condensed.build_audit.get(
            "retained_numeric_cache_bytes_sum", {}
        )
        retained_cache_bytes = int(retained_cache["retained_numeric_cache_bytes"])
        port_bytes = sum(term.Bi.nbytes + term.Di.nbytes + term.port_indices.nbytes
                         for term in port_terms.values())
        mapping_arrays = [condensed.owned_trace_original_dofs,
                          condensed.trace_constraints.owned_active_original_dofs]
        mapping_arrays.extend(a for cell in condensed.cell_recovery_maps
                              for a in (cell.interior_original_dofs, cell.trace_original_dofs))
        mapping_arrays.extend(a for pair in condensed.trace_constraints.expansion_by_original.values()
                              for a in pair)
        mapping_bytes = sum(a.nbytes for a in {id(a): a for a in mapping_arrays}.values())
        if capacity_metadata_callback is not None:
            capacity_metadata_callback(
                {
                    "p4_port_terms_count": int(len(port_terms)),
                    "p4_port_terms_Bi_bytes": int(
                        sum(term.Bi.nbytes for term in port_terms.values())
                    ),
                    "xiB_payload_estimate_bytes": int(
                        sum(term.Bi.nbytes for term in port_terms.values())
                    ),
                    "p4_port_terms_payload_bytes": int(port_bytes),
                    "p4_mapping_bytes": int(mapping_bytes),
                    "p4_local_dimension": int(condensed.build_audit["local_tensor_dimension"]),
                    "p4_interior_dimension": int(condensed.build_audit["local_interior_dimension"]),
                    "p4_trace_dimension": int(condensed.build_audit["local_trace_dimension"]),
                    "p4_raw_class_count": int(
                        condensed.build_audit["raw_tensor_class_count_global_unique"]
                    ),
                    "p4_oriented_class_count": int(
                        condensed.build_audit["oriented_schur_class_count_sum"]
                    ),
                    "source": "live_assembled_p4_port_terms_and_condensation_metadata",
                }
            )
        runtime.reserve_inventory(
            matrix_inventory_label,
            {
                "matrix_payload_bytes": _sparse_payload_bytes(
                    matrix_info, int(condensed.matrix.getSize()[0])
                ),
                "condensation_retained_numeric_bytes": retained_cache_bytes,
                "local_port_terms_bytes": port_bytes,
                "numeric_mapping_bytes": mapping_bytes,
            },
            check_rss=False,
        )
        _runtime_marker(
            runtime,
            "v18_cell_condensed_assembly_complete",
            {
                "matrix_identity": matrix_before,
                "build_audit": condensed.build_audit,
            },
        )
        factor_factory = _factor_factory_for_backend(backend)
        controls_before_symbolic = {}

        def checked_factor_factory(matrix):
            built = factor_factory(matrix)
            try:
                controls_before_symbolic.update(_controls_after_solve(built, solve_index=0))
                return built
            except BaseException:
                built.destroy()
                raise

        pre_numeric_gate, post_numeric_gate = _factor_gates(
            runtime, matrix_already_reserved=True
        )

        if factor_post_numeric_gate is not None:
            default_post_numeric_gate = post_numeric_gate

            def post_numeric_gate(facts):
                factor_post_numeric_gate(facts)
                default_post_numeric_gate(facts)

        def numeric_observer(observation):
            if factor_numeric_observer is None:
                return
            enriched = dict(observation)
            # The setup identity is already the known CSR content identity.
            # Reuse it for the durable pre-gate observer; the normal
            # post-factor check below performs the one necessary fresh hash.
            enriched["matrix_identity_before_factor"] = dict(matrix_before)
            enriched["matrix_identity_after_factor"] = None
            enriched["matrix_identity_after_factor_status"] = "pending_post_factor_hash"
            factor_numeric_observer(enriched)

        factor, factor_facts = _prepare_factor(
            condensed.matrix,
            checked_factor_factory,
            label=factor_inventory_label,
            resource_sample=lambda: _runtime_sample(runtime, "v18_factor"),
            marker=lambda name, facts: _runtime_marker(runtime, name, facts),
            pre_numeric_gate=pre_numeric_gate,
            post_numeric_gate=post_numeric_gate,
            memory_request_builder=factor_memory_request_builder,
            numeric_observer=(
                numeric_observer if factor_numeric_observer is not None else None
            ),
        )
        matrix_after = petsc_csr_content_identity(condensed.matrix)
        if matrix_after != matrix_before:
            raise RuntimeError("condensed matrix content changed during factor setup")
        runtime.check_inventory_projected(
            "v18_port_recovery", sum(term.Bi.nbytes for term in port_terms.values())
        )
        inverse = P4CellCondensedInverse(
            condensed,
            factor,
            port_terms=port_terms,
            owns_condensed=True,
            owns_factor=True,
            retain_through_postprocess_v18=(
                matrix_lifecycle_policy == "LEGACY_RETAIN_THROUGH_POSTPROCESS"
            ),
        )
        runtime.reserve_inventory(f"v18_{backend}_port_recovery", {
            "XiB_bytes": sum(a.nbytes for a in inverse._xiB_by_cell.values()),
        }, check_rss=False)
        identity, identity_sha = _operator_identity(
            common,
            resolved_payload,
            condensed,
            matrix_before,
            stage=stage,
        )
        adapter = CellCondensedFintAdapter(inverse)
        runtime.release_workspace(assembly_workspace)
        factor_facts["controls_before_symbolic"] = controls_before_symbolic
        factor_facts["numeric_raw"] = factor.info((9, 22, 29, 35, 36, 37))
        cache_audit = condensed.build_audit.get(
            "retained_numeric_cache_bytes_local", {}
        )
        stack_facts = {
            "schema": "task039extra.v18.cell-condensed-stack.v1",
            "stage": str(stage),
            "backend": str(backend),
            "matrix_identity_before_factor": matrix_before,
            "matrix_identity_after_factor": matrix_after,
            "factor": factor_facts,
            "condensation": condensed.build_audit,
            "retained_setup_cache_bytes": cache_audit,
            "internal_factor_count": 0,
            "global_interface_matrix_built": True,
            "global_dense_schur_constructed": False,
            "old_full_p4_matrix_allocated": False,
            "old_macro_objects_constructed": False,
            "retain_through_postprocess_v18": (
                matrix_lifecycle_policy == "LEGACY_RETAIN_THROUGH_POSTPROCESS"
            ),
            "matrix_lifecycle_policy": str(matrix_lifecycle_policy),
            "matrix_release_before_official_output": (
                matrix_lifecycle_policy == "MATRIX_RETAINED_BACKEND_DEPENDENCY"
            ),
            "setup_seconds": time.perf_counter() - setup_started,
            "allocation_audit": allocation_audit,
            "local_port_terms_bytes": port_bytes,
            "numeric_mapping_bytes": mapping_bytes,
        }
        _runtime_marker(runtime, "v18_condensed_factor_ready", stack_facts)
        released_after_final_residual = False

        def release_after_final_residual():
            nonlocal inverse, factor, condensed, compiled_form
            nonlocal adapter, stack_result, port_terms, mapping_arrays
            nonlocal released_after_final_residual
            if released_after_final_residual:
                return {"status": "ALREADY_RELEASED"}
            if matrix_lifecycle_policy != "MATRIX_RETAINED_BACKEND_DEPENDENCY":
                raise RuntimeError(
                    "post-KSP p4 release is only enabled for the explicit V20 policy"
                )
            _runtime_marker(
                runtime,
                "v20_p4_release_started",
                {
                    "matrix_lifecycle_policy": matrix_lifecycle_policy,
                    "factor_destroy_before_matrix": True,
                    "borrowed_backend_dependency_respected": True,
                },
            )
            # Keep the matrix alive through this final streaming observation;
            # no dense or copied global CSR is created.
            matrix_identity_started = time.perf_counter()
            matrix_identity_before_release = petsc_csr_content_identity(
                condensed.matrix
            )
            matrix_identity_before_release_seconds = (
                time.perf_counter() - matrix_identity_started
            )
            matrix_identity_before_release_matches_setup = (
                matrix_identity_before_release == matrix_before
            )
            matrix_identity_before_release_matches_factor = (
                matrix_identity_before_release == matrix_after
            )
            matrix_identity_before_release_consistent = bool(
                matrix_identity_before_release_matches_setup
                and matrix_identity_before_release_matches_factor
            )
            release_matrix_facts = {
                "matrix_identity_before_release": matrix_identity_before_release,
                "matrix_identity_before_release_matches_setup": (
                    matrix_identity_before_release_matches_setup
                ),
                "matrix_identity_before_release_matches_factor": (
                    matrix_identity_before_release_matches_factor
                ),
                "matrix_identity_before_release_consistent": (
                    matrix_identity_before_release_consistent
                ),
                "matrix_identity_before_release_seconds": (
                    matrix_identity_before_release_seconds
                ),
            }
            # Persist the observation before evaluating it so a changed
            # matrix leaves durable negative evidence.
            _runtime_marker(
                runtime,
                "v20_p4_matrix_identity_before_release",
                release_matrix_facts,
            )
            stack_facts.update(release_matrix_facts)
            if not matrix_identity_before_release_consistent:
                raise RuntimeError(
                    "condensed matrix content changed before V20 p4 release"
                )
            if inverse is not None:
                inverse.destroy()
                if adapter is not None:
                    adapter.inverse = None
                inverse = None
                factor = None
                condensed = None
            elif factor is not None:
                destroy = getattr(factor, "destroy", None)
                if callable(destroy):
                    destroy()
                factor = None
            if condensed is not None:
                condensed.destroy()
                condensed = None
            port_terms.clear()
            mapping_arrays.clear()
            if adapter is not None:
                adapter.inverse = None
            adapter = None
            if stack_result is not None:
                stack_result["fint"] = None
                stack_result["inverse"] = None
                stack_result["factor"] = None
                stack_result["condensed"] = None
                stack_result["released_after_final_residual"] = True
            compiled_form = None
            released_after_final_residual = True
            runtime.release_inventory(factor_inventory_label)
            runtime.release_inventory(matrix_inventory_label)
            runtime.release_inventory(f"v18_{backend}_port_recovery")
            runtime.release_workspace(assembly_workspace)
            facts = {
                "status": "RELEASED",
                "released_after_final_residual": True,
                "matrix_lifecycle_policy": matrix_lifecycle_policy,
                "factor_destroy_before_matrix": True,
                "borrowed_backend_dependency_respected": True,
                **release_matrix_facts,
            }
            _runtime_marker(runtime, "v20_p4_release_complete", facts)
            return facts

        stack_result = {
            "schema": stack_facts["schema"],
            "fint": adapter,
            "inverse": inverse,
            "factor": factor,
            "condensed": condensed,
            "operator_identity": identity,
            "operator_identity_sha256": identity_sha,
            "stack_facts": stack_facts,
            "internal_factor_count": 0,
        }
        if matrix_lifecycle_policy == "MATRIX_RETAINED_BACKEND_DEPENDENCY":
            stack_result["release_after_final_residual"] = release_after_final_residual
        yield stack_result
    finally:
        if inverse is not None:
            inverse.destroy()
            inverse = None
            factor = None
            condensed = None
        elif factor is not None:
            destroy = getattr(factor, "destroy", None)
            if callable(destroy):
                destroy()
            factor = None
        if condensed is not None:
            condensed.destroy()
            condensed = None
        v20_lifecycle = (
            matrix_lifecycle_policy == "MATRIX_RETAINED_BACKEND_DEPENDENCY"
        )
        port_terms.clear()
        mapping_arrays.clear()
        if v20_lifecycle and adapter is not None:
            adapter.inverse = None
        if v20_lifecycle:
            adapter = None
        if v20_lifecycle and stack_result is not None:
            stack_result["fint"] = None
            stack_result["inverse"] = None
            stack_result["factor"] = None
            stack_result["condensed"] = None
        if v20_lifecycle or compiled_form_holder is not None:
            compiled_form = None
        release_inventory = getattr(runtime, "release_inventory", None)
        if callable(release_inventory):
            release_inventory(factor_inventory_label)
            release_inventory(matrix_inventory_label)
            release_inventory(f"v18_{backend}_port_recovery")
        runtime.release_workspace(assembly_workspace)
        if owns_compiled_form and compiled_form is not None:
            del compiled_form


def cell_condensed_stack_factory(
    *,
    backend: str = "exact",
    compiled_form: Any | None = None,
    compiled_form_holder: dict[str, Any] | None = None,
    matrix_lifecycle_policy: str = "LEGACY_RETAIN_THROUGH_POSTPROCESS",
    factor_memory_request_builder=None,
    factor_numeric_observer=None,
    factor_post_numeric_gate=None,
):
    """Return the small factory consumed by the existing V14 outer helper."""

    def factory(runtime, common, resolved_payload, *, stage):
        return cell_condensed_stack(
            runtime,
            common,
            resolved_payload,
            stage=stage,
            backend=backend,
            compiled_form=compiled_form,
            compiled_form_holder=compiled_form_holder,
            matrix_lifecycle_policy=matrix_lifecycle_policy,
            factor_memory_request_builder=factor_memory_request_builder,
            factor_numeric_observer=factor_numeric_observer,
            factor_post_numeric_gate=factor_post_numeric_gate,
        )

    return factory


def run_cell_condensed_fullspace_stage(
    runtime: Any,
    common: Mapping[str, Any],
    resolved_payload: Mapping[str, Any],
    *,
    stage: str,
    predecessor: Mapping[str, Any],
    backend: str,
) -> dict[str, Any]:
    """Run the existing p6 BAL_H helper with the V18 ``fint`` stack."""

    from .physical_p4_schur_v14 import _v14_q4_q5_fullspace

    return _v14_q4_q5_fullspace(
        runtime,
        dict(common),
        resolved_payload,
        stage=stage,
        predecessor=predecessor,
        stack_factory=cell_condensed_stack_factory(backend=backend),
    )


def _controls_after_solve(factor: Any, *, solve_index: int) -> dict[str, Any]:
    return {
        "stage": f"solve_{solve_index}_after",
        "icntl": {str(i): factor.try_get_icntl(i) for i in (2, 3, 4, 6, 7, 8, 10, 14, 18, 22, 23, 28, 29, 35, 36, 37, 38)},
        "cntl": {str(i): factor.try_get_cntl(i) for i in (1, 3, 4, 7)},
    }


def _native_residual_packet(common, rhs, solution, alpha):
    from .physical_p4_schur_v14 import _augmented_residual_arrays
    from src.solvers.fullspace_p4_blr import (
        augmented_residual_identity, native_a4_residual_from_augmented,
    )

    carrier = common["p4"]["dtn_action"].carrier
    facts, native, volume, top, port = _augmented_residual_arrays(
        common["p4"]["volume_action"], common["p4"]["physical_action"],
        carrier, rhs, solution, alpha,
    )
    native, volume, top, port = -native, -volume, -top, -port
    action = rhs.array - native
    identity = augmented_residual_identity(
        native, top, port, carrier, rhs_norm=float(rhs.norm()),
        native_action_norm=float(np.linalg.norm(action)),
    )
    reconstructed = native_a4_residual_from_augmented(top, port, carrier)
    return facts, identity, {
        "native_A4_residual": native, "native_volume_top_residual": volume,
        "native_action": action, "augmented_top_residual": top,
        "port_residual": port, "native_identity_reconstructed": reconstructed,
    }


def _run_v18_p4_control(runtime, common, resolved_payload, *, root, stage, backend):
    """One factor, three immediately saved inputs and at most three extra calls."""
    import time
    from .physical_p4_schur_v14 import (
        _field_metrics, _prepare_reviewed_rhs, _release_reviewed_rhs,
        _save_packet, _storage_rhs, _write_json,
    )

    reviewed = None
    records, additional, main_solutions = [], [], []
    gates = runtime.contract["gates"]
    # Includes reviewed vectors/maps, six retained solutions and current
    # native/augmented residual arrays. The existing metric and packet writers
    # independently register their simultaneously live temporary work.
    runtime.reserve_workspace("v18_control_vectors", 64 << 20)
    progress = {"stage": stage, "backend": backend, "solve_records": records,
                "additional_solve_records": additional, "source_sha": runtime.source_sha}
    try:
        reviewed = _prepare_reviewed_rhs(runtime, common, resolved_payload, root, 53084)
        if tuple(item["stem"] for item in reviewed) != _RHS_STEMS:
            raise ValueError("frozen RHS order changed")
        with cell_condensed_stack(runtime, common, resolved_payload, stage=stage, backend=backend) as stack:
            inverse, factor = stack["inverse"], stack["factor"]
            local_lu_ids = {key: (id(lu[0]), id(lu[1]))
                            for key, lu in inverse.condensed.interior_lu_by_class.items()}
            mapping = _save_packet(runtime.directory, "v18_mapping_identity", {
                "operator_identity": stack["operator_identity"],
                "active_rows": inverse.condensed.trace_constraints.owned_active_original_dofs,
                "slave_rows": inverse._slave_original,
            }, runtime=runtime)
            progress.update(stack=stack["stack_facts"], mapping_packet=mapping,
                            factor=stack["stack_facts"]["factor"],
                            matrix_identity_before_factor=inverse.matrix_identity,
                            matrix_identity_after_factor=stack["stack_facts"]["matrix_identity_after_factor"])

            def run_one(values, label, reference=None, identity=None, expected=None):
                runtime.set_phase("solve")
                started = time.perf_counter()
                rhs = _storage_rhs(common["levels"]["spaces"][4], values)
                solution = None
                try:
                    before = factor.solve_calls
                    apply_started = time.perf_counter()
                    solution = inverse.apply(rhs)
                    apply_seconds = time.perf_counter() - apply_started
                    after = factor.solve_calls
                    c = np.asarray(solution.array).copy()
                    alpha = inverse.last_port_solution.copy()
                    native_started = time.perf_counter()
                    facts, closure, arrays = _native_residual_packet(common, rhs, solution, alpha)
                    native_seconds = time.perf_counter() - native_started
                    field_started = time.perf_counter()
                    field = (_field_metrics(runtime, common, [c], [reference])[0]
                             if reference is not None else None)
                    field_seconds = time.perf_counter() - field_started
                    row = {
                        "stem": label, "factor_solve_calls_before": before,
                        "factor_solve_calls_after": after, "factor_solve_call_delta": after - before,
                        "rhs_input_unchanged": bool(np.array_equal(values, rhs.array)),
                        "hidden_refinement": False, "controls_after_solve": _controls_after_solve(factor, solve_index=after),
                        "native_A4_relative_residual": facts["native_A4_relative"],
                        "augmented_residual": facts, "native_residual_identity": closure,
                        "slave_nonzero_count": int(np.count_nonzero(c[inverse._slave_original])),
                        "symbolic_calls": factor.symbolic_calls, "numeric_calls": factor.numeric_calls,
                        "local_lu_identity_unchanged": local_lu_ids == {
                            key: (id(lu[0]), id(lu[1])) for key, lu in inverse.condensed.interior_lu_by_class.items()},
                        "local_lu_count": len(local_lu_ids), "field_metrics": field,
                        "apply_seconds": apply_seconds, "native_evaluation_seconds": native_seconds,
                        "field_metric_seconds": field_seconds,
                        "inverse_call": dict(inverse.last_audit),
                        "solution_sha256": _identity_sha(c),
                    }
                    if expected is not None:
                        row["linearity_error_norm"] = float(np.linalg.norm(c - expected))
                        row["linearity_operation_scale"] = max(
                            sum(float(np.linalg.norm(x)) for x in main_solutions), np.finfo(float).tiny)
                        row["linearity_relative"] = row["linearity_error_norm"] / row["linearity_operation_scale"]
                    directory = runtime.directory / ("rhs_packets" if reference is not None else "additional_rhs")
                    save_started = time.perf_counter()
                    packet = _save_packet(directory, label, {
                        "schema": "task039extra.v18.rhs-packet.v1", "identity": identity or {"stem": label},
                        "solve": row, "g": values, "x_storage": c, "alpha": alpha, **arrays,
                    }, runtime=runtime)
                    row["packet_save_seconds"] = time.perf_counter() - save_started
                    row["elapsed_seconds"] = time.perf_counter() - started
                    packet["solve"] = dict(row)
                    _write_json(directory / f"{label}.json", packet)
                    row["packet"] = packet
                    runtime.sample(f"{label}_saved_factor_live")
                    return row, c
                finally:
                    if solution is not None:
                        solution.destroy()
                    rhs.destroy()

            for item in reviewed:
                identity = {key: item[key] for key in (
                    "stem", "logical_rhs", "input_json", "input_npz", "input_sha256",
                    "input_npz_sha256", "g_sha256", "reference_json", "reference_npz",
                    "reference_json_sha256", "reference_npz_sha256")}
                row, c = run_one(item["rhs"], item["stem"], item["reference_solution"], identity)
                records.append(row)
                main_solutions.append(c)
                _write_json(runtime.directory / "v18_control_progress.json", progress)
            # The resource endpoint follows the saved third RHS and its sample.
            runtime.marker("u2_main_rhs_window_complete", {"rhs_count": 3, "backend": backend})
            if backend == "exact":
                for label, left, right, coefficient in (
                    ("extra_01_repeat", 0, None, 0),
                    ("extra_01_plus_i02", 0, 1, 1j),
                    ("extra_09_minus_01", 2, 0, -1),
                ):
                    values = reviewed[left]["rhs"]
                    expected = main_solutions[left]
                    if right is not None:
                        values = values + coefficient * reviewed[right]["rhs"]
                        expected = expected + coefficient * main_solutions[right]
                    row, _ = run_one(values, label, expected=expected)
                    additional.append(row)
                    _write_json(runtime.directory / "v18_control_progress.json", progress)
            from src.solvers.p4_cell_condensed_inverse import petsc_csr_content_identity
            final_matrix = petsc_csr_content_identity(stack["condensed"].matrix)
            progress["matrix_identity_after_calls"] = final_matrix
            progress["factor_call_counts"] = {
                "symbolic": factor.symbolic_calls, "numeric": factor.numeric_calls,
                "solve": factor.solve_calls, "local_lu": len(local_lu_ids)}
            progress["factor"]["numeric_raw"] = factor.info((9, 22, 29, 35, 36, 37))
            progress["factor"]["controls_after_calls"] = _controls_after_solve(factor, solve_index=factor.solve_calls)
            runtime.sample("v18_all_calls_complete_factor_live")
            runtime.marker("v18_control_complete", progress["factor_call_counts"])
            main_ok = len(records) == 3 and all(
                r["native_A4_relative_residual"] <= gates["native_A4_relative_residual"]
                and r["field_metrics"]["field_l2_relative"] <= gates["field_l2_and_scaled_curl"]
                and r["field_metrics"]["scaled_curl_relative"] <= gates["field_l2_and_scaled_curl"]
                for r in records)
            structural_ok = final_matrix == inverse.matrix_identity and all(
                r["factor_solve_call_delta"] == 1 and r["numeric_calls"] == r["symbolic_calls"] == 1
                and r["local_lu_identity_unchanged"] and r["slave_nonzero_count"] == 0
                and r["rhs_input_unchanged"] and r["native_residual_identity"]["relative"] <= 1e-10
                for r in records + additional)
            extra_ok = backend != "exact" or (len(additional) == 3 and all(
                r["native_A4_relative_residual"] <= 1e-10 and r["linearity_relative"] <= 1e-10
                for r in additional))
            passed = bool(main_ok and structural_ok and extra_ok)
            progress.update(status=f"{stage}_{'PASS' if passed else 'GATE_FAIL'}", stage_pass=passed,
                            quality_pass=bool(main_ok), common_correct=bool(structural_ok),
                            additional_quality_pass=bool(extra_ok), official_result=False,
                            result_classification="P4_CONTROL_PASS" if passed else "P4_CONTROL_GATE_FAIL")
            _write_json(runtime.directory / "v18_control_progress.json", progress)
        return progress
    finally:
        _release_reviewed_rhs(reviewed)
        runtime.release_workspace("v18_control_vectors")


def _prerequisite(runtime, stage, backend):
    """Consume a hash-bound independent selection, never select inside a PC."""
    from .physical_p4_schur_v14 import _sha256_file

    if stage == "U2_EXACT_CONTROL":
        return {"required_stage": "U0", "source_reviewed_before_launch": True}
    path = runtime._ledger_path.parent / "selection.json"
    record = json.loads(path.read_text())
    if record["batch_identity"] != "review_v18_p4_cell_condensed":
        raise ValueError("selection batch identity changed")
    for descriptor in record["evidence"]:
        if _sha256_file(Path(descriptor["path"])) != descriptor["sha256"]:
            raise ValueError("selection evidence content changed")
    if stage == "U3_BLR_CONTROL":
        allowed = record.get("exact_control_qualified") is True
    elif stage == "U4_ORIGINAL":
        allowed = record.get("admit_u4") is True and record.get("selected_backend") == backend
    elif stage == "U4_EXACT_FALLBACK":
        allowed = backend == "exact" and record.get("exact_fallback_authorized") is True
    elif stage == "U5_NOTCH":
        allowed = record.get("original_passed") is True and record.get("original_passed_backend") == backend
    else:
        allowed = True
    if not allowed:
        raise ValueError(f"{stage} has no matching qualified predecessor")
    return {"selection_path": str(path), "selection_sha256": _sha256_file(path), **record}


def run_physical_p4_cell_condensed_v18(resolved_payload, run_directory, *, source_sha):
    """Execute the selected reviewed stage under the existing parent watchdog."""
    from src.io.input_validation import simulation_config_3d_from_normalized
    from .physical_p4_schur_v14 import (
        V14ResourceStop, _V14Runtime, _abi_facts, _build_common, _destroy_common,
        _repo_root, _v14_known_preallocation_gate, _write_json,
    )

    directory = Path(run_directory).resolve()
    profile, stage = (str(resolved_payload["solver"][key]) for key in ("preconditioner", "stage"))
    contract = profile_facts(profile)
    backend = contract["backend"]
    summary = {"schema": "task039extra.v18.worker-summary.v1", "profile": profile,
               "stage": stage, "source_sha": source_sha, "backend": backend,
               "status": "STARTED", "official_result": False, "stage_pass": False}
    runtime = common = None
    handlers = {}
    try:
        if profile not in {CELL_CONDENSED_EXACT_PROFILE, CELL_CONDENSED_BLR_PROFILE}:
            raise ValueError("unexpected V18 profile")
        if resolved_payload.get("derived", {}).get("physical_intermediate_profile") != contract:
            raise ValueError("resolved V18 profile changed")
        if len(source_sha) != 40:
            raise ValueError("full source SHA required")
        summary["abi"] = _abi_facts()
        runtime = _V14Runtime(directory, stage, contract, root=_repo_root(), source_sha=source_sha,
                              batch_identity="review_v18_p4_cell_condensed", evidence_prefix="v18")
        summary.update(shared_budget=runtime.shared_budget, time_policy=runtime.time_policy)
        for signum in (signal.SIGTERM, signal.SIGINT):
            handlers[signum] = signal.signal(signum, lambda *_args: setattr(runtime, "stop_requested", True))
        runtime.sample("v18_preflight")
        if stage in {"U0_PREFLIGHT", "U1_CONTROL_BRIDGE", "U6_FINALIZE"}:
            # These stages review saved evidence outside the PDE worker. A
            # successful process launch alone cannot qualify their checks.
            raise ValueError(f"{stage} is an evidence review stage, not a numerical worker stage")
        else:
            predecessor = _prerequisite(runtime, stage, backend)
            _v14_known_preallocation_gate(runtime, stage, include_common=True, include_matrices=False)
            common = _build_common(runtime, simulation_config_3d_from_normalized(resolved_payload))
            if stage in {"U2_EXACT_CONTROL", "U3_BLR_CONTROL"}:
                if (stage == "U2_EXACT_CONTROL") != (backend == "exact"):
                    raise ValueError("control stage/backend mismatch")
                result = _run_v18_p4_control(runtime, common, resolved_payload,
                                             root=runtime.root, stage=stage, backend=backend)
            elif stage in {"U4_ORIGINAL", "U4_EXACT_FALLBACK", "U5_NOTCH"}:
                result = run_cell_condensed_fullspace_stage(
                    runtime, common, resolved_payload, stage=stage, predecessor=predecessor, backend=backend)
            else:
                raise ValueError(f"unknown V18 stage {stage}")
            summary.update(result)
    except V14ResourceStop as exc:
        summary.update(status="CONTROLLED_STOP", stage_pass=False,
                       result_classification=exc.classification, error=str(exc))
    except Exception as exc:
        summary.update(status="FAILED", stage_pass=False, result_classification="WORKER_FAILED",
                       error={"type": type(exc).__name__, "message": str(exc)})
    finally:
        if runtime is not None:
            progress = directory / "v18_control_progress.json"
            if progress.exists() and "solve_records" not in summary:
                summary["partial_control_evidence"] = json.loads(progress.read_text())
            try:
                runtime.set_phase("cleanup")
                if common is not None:
                    _destroy_common(common, runtime)
                runtime.sample("v18_post_cleanup")
            except Exception as exc:
                summary["cleanup_error"] = {"type": type(exc).__name__, "message": str(exc)}
                summary.update(stage_pass=False, status="FAILED", result_classification="CLEANUP_FAILED")
        for signum, handler in handlers.items():
            signal.signal(signum, handler)
        _write_json(directory / "physical_p4_cell_condensed_v18_summary.json", summary)
        if runtime is not None:
            runtime.marker("v18_worker_complete", summary)
    return {"passed": bool(summary["stage_pass"]),
            "errors": [] if summary["stage_pass"] else [str(summary.get("error", summary["status"]))],
            "summary": summary, "numerical_output_directory": str(directory / "numerical_output")}
