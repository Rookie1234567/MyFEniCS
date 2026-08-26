"""Tiny V6 exact-qualification loader and checkpoint-driver contracts."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_exact_qualification import (
    ExactQualificationContractError,
    V5_VECTOR_SCHEMA,
    V5_VECTOR_SIDE,
    canonical_values_roundtrip_error,
    hash_array_bytes_sha256,
    load_and_condense_exact_rhs,
    load_owner_local_vector,
    load_owner_local_vector_collective,
    make_live_canonical_roundtrip_callback,
    rank_local_shard_binding_sha256,
    run_exact_qualification_family,
    run_exact_interface_fgmres,
    _next_iteration_boundary,
    validate_owner_vector_descriptor,
)


HEX = "a" * 64
SOURCE_SHA = "b" * 40
SOURCE_DEFINITION_SHA = "c" * 64


def _key_set_sha(keys: list[dict[str, int]]) -> str:
    tokens = [
        json.dumps(key, sort_keys=True, separators=(",", ":")) for key in keys
    ]
    return hashlib.sha256("\n".join(sorted(tokens)).encode()).hexdigest()


def _write_json(path: Path, payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, indent=2).encode() + b"\n"
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def _make_descriptor(
    root: Path,
    *,
    rank: int = 0,
    mpi_size: int = 1,
    label: str = "synthetic_rhs",
    global_size: int = 2,
    owner_range: tuple[int, int] = (0, 2),
    canonical_keys: list[dict[str, int]] | None = None,
    canonical_values: np.ndarray | None = None,
    owner_values: np.ndarray | None = None,
    canonical_key_set_sha: str | None = None,
    global_sha256: str | None = None,
) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    canonical_keys = canonical_keys or [
        {"row": 0},
        {"row": 1},
        {"row": 2},
    ]
    canonical_values = (
        np.asarray([1.0 + 0.5j, 2.0 - 0.25j, 3.0 + 0.75j], dtype=np.complex128)
        if canonical_values is None
        else np.asarray(canonical_values, dtype=np.complex128)
    )
    owner_span = owner_range[1] - owner_range[0]
    if owner_values is None:
        if owner_span == 2 and canonical_values.size == 3:
            owner_values = np.asarray(
                [canonical_values[0], canonical_values[2]], dtype=np.complex128
            )
        else:
            owner_values = np.asarray(canonical_values[:owner_span], dtype=np.complex128)
    else:
        owner_values = np.asarray(owner_values, dtype=np.complex128)
    if global_sha256 is None:
        local_array_sha256 = hash_array_bytes_sha256(canonical_values)
        global_sha256 = hashlib.sha256(
            local_array_sha256.encode("ascii")
        ).hexdigest()
    canonical_path = root / f"rank{rank:04d}_canonical.npy"
    owner_path = root / f"rank{rank:04d}_owner.npy"
    layout_path = root / f"rank{rank:04d}_canonical_active_layout.json"
    np.save(canonical_path, canonical_values, allow_pickle=False)
    np.save(owner_path, owner_values, allow_pickle=False)
    key_set_sha = (
        _key_set_sha(canonical_keys)
        if canonical_key_set_sha is None
        else canonical_key_set_sha
    )
    layout = {
        "canonical_keys": canonical_keys,
        "canonical_key_set_sha256": key_set_sha,
        "global_size": global_size,
        "local_size": len(canonical_keys),
        "ownership_range": list(owner_range),
        "rank": rank,
        "mpi_size": mpi_size,
    }
    layout_sha = _write_json(layout_path, layout)
    provenance = {
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "selected_manifest_sha256": HEX,
        "selected_identity_sha256": HEX,
        "resolved_config_sha256": HEX,
        "source_sha": SOURCE_SHA,
    }
    descriptor = {
        "schema": V5_VECTOR_SCHEMA,
        "side": V5_VECTOR_SIDE,
        "label": label,
        "role": "rhs",
        "dtype": "complex128",
        "global_size": global_size,
        "local_size": owner_range[1] - owner_range[0],
        "ownership_range": list(owner_range),
        "array_path": canonical_path.name,
        "array_sha256": hash_array_bytes_sha256(canonical_values),
        "owner_row_array_path": owner_path.name,
        "owner_row_array_sha256": hash_array_bytes_sha256(owner_values),
        "owner_row_order": "petsc_current_ownership_range",
        "canonical_layout_path": layout_path.name,
        "canonical_layout_sha256": layout_sha,
        "canonical_key_set_sha256": key_set_sha,
        "canonical_key_count_local": len(canonical_keys),
        "global_sha256": global_sha256,
        "source_definition_sha256": SOURCE_DEFINITION_SHA,
        "bare_f_operator_hash": HEX,
        "canonical_to_current_roundtrip_relative": 0.0,
        "rank_local_shard_binding_sha256": HEX,
        "raw_global_row_remap": False,
        "source_provenance": provenance,
        "source_definition": {
            "source_definition_sha256": SOURCE_DEFINITION_SHA,
            "input_sha256": HEX,
            "physical_model_sha256": HEX,
            "selected_manifest_sha256": HEX,
            "selected_identity_sha256": HEX,
            "resolved_config_sha256": HEX,
            "bare_f_operator_hash": HEX,
            "canonical_key_set_sha256": key_set_sha,
            "rhs_repeat": {
                "finite": True,
                "pass": True,
                "relative_difference": 0.0,
            },
        },
    }
    descriptor["vector_identity"] = {
        key: descriptor[key]
        for key in (
            "array_sha256",
            "canonical_key_count_local",
            "canonical_key_set_sha256",
            "dtype",
            "global_size",
            "local_size",
            "owner_row_array_sha256",
            "owner_row_order",
            "ownership_range",
            "raw_global_row_remap",
            "global_sha256",
            "canonical_to_current_roundtrip_relative",
        )
    }
    descriptor["rank_local_shard_binding_sha256"] = rank_local_shard_binding_sha256(
        rank=rank,
        label=label,
        role="rhs",
        source_definition_sha256=SOURCE_DEFINITION_SHA,
        key_set_sha256=key_set_sha,
        canonical_layout_sha256=layout_sha,
        identity=descriptor["vector_identity"],
        source_provenance=provenance,
        bare_f_operator_hash=HEX,
        rhs_repeat=descriptor["source_definition"]["rhs_repeat"],
    )
    return descriptor


def _load_callback(owner_keys: list[dict[str, int]], seen: list[bool]):
    def callback(
        layout_audit: dict[str, Any],
        vector: PETSc.Vec,
        canonical_values: np.ndarray,
    ) -> float:
        seen.append(bool(vector))
        owner_values = np.asarray(vector.array, dtype=np.complex128).copy()
        return canonical_values_roundtrip_error(
            layout_audit["canonical_tokens"],
            canonical_values,
            owner_keys,
            owner_values,
        )

    return callback


class _LiveCanonicalAdapter:
    def __init__(
        self,
        frozen_tokens: tuple[str, ...],
        frozen_values: np.ndarray,
        owner_keys: list[dict[str, int]],
    ) -> None:
        self.frozen_tokens = frozen_tokens
        self.frozen_values = np.asarray(frozen_values, dtype=np.complex128).copy()
        self.owner_keys = owner_keys
        self.packet_calls = 0
        self.roundtrip_calls = 0
        self.vector_alive: list[bool] = []

    def canonical_packets_for_vector(
        self,
        _system: Any,
        vector: PETSc.Vec,
    ) -> tuple[tuple[str, ...], np.ndarray]:
        self.packet_calls += 1
        self.vector_alive.append(bool(vector))
        return (
            self.frozen_tokens,
            self.frozen_values.copy(),
        )

    def canonical_to_current_roundtrip_relative(
        self,
        _system: Any,
        tokens: tuple[str, ...],
        values: np.ndarray,
        vector: PETSc.Vec,
    ) -> float:
        self.roundtrip_calls += 1
        assert tokens == self.frozen_tokens
        np.testing.assert_allclose(values, self.frozen_values)
        return canonical_values_roundtrip_error(
            tokens,
            values,
            self.owner_keys,
            np.asarray(vector.array, dtype=np.complex128),
        )


def test_loader_runs_live_roundtrip_after_owner_vec_is_filled(tmp_path: Path) -> None:
    descriptor = _make_descriptor(tmp_path)
    frozen_tokens = tuple(
        json.dumps(key, sort_keys=True, separators=(",", ":"))
        for key in ({"row": 0}, {"row": 1}, {"row": 2})
    )
    frozen_values = np.asarray(
        [1.0 + 0.5j, 2.0 - 0.25j, 3.0 + 0.75j], dtype=np.complex128
    )
    adapter = _LiveCanonicalAdapter(
        frozen_tokens,
        frozen_values,
        [{"row": 0}, {"row": 2}],
    )
    live_roundtrip = make_live_canonical_roundtrip_callback(
        adapter,
        canonical_packets_for_vector=adapter.canonical_packets_for_vector,
        canonical_to_current_roundtrip_relative=(
            adapter.canonical_to_current_roundtrip_relative
        ),
        frozen_tokens=frozen_tokens,
        frozen_values=frozen_values,
    )

    vector, audit = load_owner_local_vector(
        descriptor,
        base_directory=tmp_path,
        comm=MPI.COMM_SELF,
        canonical_roundtrip=live_roundtrip,
        expected_source_sha256=SOURCE_SHA,
        expected_input_sha256=HEX,
        expected_physical_model_sha256=HEX,
        expected_selected_manifest_sha256=HEX,
        expected_resolved_config_sha256=HEX,
        expected_operator_hash=HEX,
    )
    try:
        assert adapter.vector_alive == [True]
        assert adapter.packet_calls == 1
        assert adapter.roundtrip_calls == 1
        assert audit["canonical_roundtrip_relative"] <= 1.0e-12
        assert audit["canonical_values_retained"] is False
        assert audit["owner_row_values_not_row_ids"] is True
        np.testing.assert_allclose(vector.array, [1.0 + 0.5j, 3.0 + 0.75j])
    finally:
        vector.destroy()


def test_producer_and_qualification_binding_hashes_are_identical(
    tmp_path: Path,
) -> None:
    from src.solvers.hybrid_bare_f_authority import (
        _rank_local_shard_binding_sha256 as producer_binding,
    )

    descriptor = _make_descriptor(tmp_path)
    identity = descriptor["vector_identity"]
    source_definition = descriptor["source_definition"]
    payload = {
        "rank": 0,
        "label": descriptor["label"],
        "role": descriptor["role"],
        "source_definition_sha256": descriptor["source_definition_sha256"],
        "key_set_sha256": descriptor["canonical_key_set_sha256"],
        "canonical_layout_sha256": descriptor["canonical_layout_sha256"],
        "identity": identity,
        "source_provenance": descriptor["source_provenance"],
        "bare_f_operator_hash": descriptor["bare_f_operator_hash"],
        "rhs_repeat": source_definition["rhs_repeat"],
    }
    assert producer_binding(**payload) == rank_local_shard_binding_sha256(**payload)


def test_live_roundtrip_rejects_tampered_persisted_layout_tokens() -> None:
    frozen_tokens = ("{\"row\":0}", "{\"row\":1}")
    frozen_values = np.asarray([1.0 + 0.0j, 2.0 + 0.0j], dtype=np.complex128)
    adapter = _LiveCanonicalAdapter(
        frozen_tokens,
        frozen_values,
        [{"row": 0}, {"row": 1}],
    )
    callback = make_live_canonical_roundtrip_callback(
        adapter,
        canonical_packets_for_vector=adapter.canonical_packets_for_vector,
        canonical_to_current_roundtrip_relative=(
            adapter.canonical_to_current_roundtrip_relative
        ),
        frozen_tokens=frozen_tokens,
        frozen_values=frozen_values,
    )
    vector = PETSc.Vec().createMPI((2, 2), comm=MPI.COMM_SELF)
    vector.array[:] = frozen_values
    vector.assemble()
    try:
        for tampered_tokens in (
            (frozen_tokens[1], frozen_tokens[0]),
            ("{\"row\":99}", frozen_tokens[1]),
        ):
            with pytest.raises(
                ExactQualificationContractError,
                match="persisted canonical layout tokens",
            ):
                callback(
                    {"canonical_tokens": tampered_tokens},
                    vector,
                    frozen_values,
                )
        assert adapter.packet_calls == 0
        assert adapter.roundtrip_calls == 0
    finally:
        vector.destroy()


class _TinyCondensedRhsAction:
    def __init__(self) -> None:
        self.seen_active_values: np.ndarray | None = None

    def build_condensed_rhs_from_active_vector(
        self,
        active_rhs: PETSc.Vec,
    ) -> tuple[PETSc.Vec, dict[int, PETSc.Vec], PETSc.Vec]:
        self.seen_active_values = np.asarray(active_rhs.array, dtype=np.complex128).copy()
        gamma_rhs = active_rhs.duplicate()
        active_rhs.copy(gamma_rhs)
        interior_rhs = {}
        for group in range(3):
            interior_rhs[group] = active_rhs.duplicate()
            active_rhs.copy(interior_rhs[group])
        condensed_rhs = active_rhs.duplicate()
        active_rhs.copy(condensed_rhs)
        return gamma_rhs, interior_rhs, condensed_rhs


def test_loader_consumer_adapter_returns_caller_owned_condensed_rhs(
    tmp_path: Path,
) -> None:
    descriptor = _make_descriptor(tmp_path)
    frozen_tokens = tuple(
        json.dumps(key, sort_keys=True, separators=(",", ":"))
        for key in ({"row": 0}, {"row": 1}, {"row": 2})
    )
    frozen_values = np.asarray(
        [1.0 + 0.5j, 2.0 - 0.25j, 3.0 + 0.75j], dtype=np.complex128
    )
    live_adapter = _LiveCanonicalAdapter(
        frozen_tokens,
        frozen_values,
        [{"row": 0}, {"row": 2}],
    )
    live_roundtrip = make_live_canonical_roundtrip_callback(
        live_adapter,
        canonical_packets_for_vector=live_adapter.canonical_packets_for_vector,
        canonical_to_current_roundtrip_relative=(
            live_adapter.canonical_to_current_roundtrip_relative
        ),
        frozen_tokens=frozen_tokens,
        frozen_values=frozen_values,
    )
    action = _TinyCondensedRhsAction()
    bundle = load_and_condense_exact_rhs(
        descriptor,
        base_directory=tmp_path,
        action=action,
        canonical_roundtrip=live_roundtrip,
        comm=MPI.COMM_SELF,
        expected_source_sha256=SOURCE_SHA,
        expected_input_sha256=HEX,
        expected_physical_model_sha256=HEX,
        expected_selected_manifest_sha256=HEX,
        expected_resolved_config_sha256=HEX,
        expected_operator_hash=HEX,
    )
    vectors = [
        bundle.active_rhs,
        bundle.gamma_rhs,
        bundle.condensed_rhs,
        *bundle.interior_rhs_by_group.values(),
    ]
    try:
        assert bundle.audit["condensed_rhs_built"] is True
        assert bundle.compact_audit()["numeric_allgather"] is False
        assert len(bundle.interior_rhs_by_group) == 3
        assert all(bool(vector) for vector in vectors)
        np.testing.assert_allclose(
            action.seen_active_values,
            [1.0 + 0.5j, 3.0 + 0.75j],
        )
        json.dumps(bundle.compact_audit())
    finally:
        bundle.destroy()
        bundle.destroy()
    assert all(not bool(vector) for vector in vectors)


class _RaisingCondensedRhsAction:
    def __init__(self) -> None:
        self.seen_active_rhs: PETSc.Vec | None = None

    def build_condensed_rhs_from_active_vector(self, active_rhs: PETSc.Vec) -> Any:
        self.seen_active_rhs = active_rhs
        raise RuntimeError("builder sentinel")


class _InvalidTupleCondensedRhsAction:
    def __init__(self) -> None:
        self.created: list[PETSc.Vec] = []
        self.seen_active_rhs: PETSc.Vec | None = None

    def build_condensed_rhs_from_active_vector(self, active_rhs: PETSc.Vec) -> Any:
        self.seen_active_rhs = active_rhs
        gamma_rhs = active_rhs.duplicate()
        interior_rhs = {
            group: active_rhs.duplicate() for group in range(3)
        }
        self.created = [gamma_rhs, *interior_rhs.values()]
        return gamma_rhs, interior_rhs


class _InvalidMemberCondensedRhsAction(_InvalidTupleCondensedRhsAction):
    def build_condensed_rhs_from_active_vector(self, active_rhs: PETSc.Vec) -> Any:
        self.seen_active_rhs = active_rhs
        gamma_rhs = active_rhs.duplicate()
        interior_rhs = {
            group: active_rhs.duplicate() for group in range(3)
        }
        self.created = [gamma_rhs, *interior_rhs.values()]
        return gamma_rhs, interior_rhs, object()


def _adapter_descriptor_and_callback(
    tmp_path: Path,
    *,
    label: str = "synthetic_rhs",
) -> tuple[dict[str, Any], Any]:
    descriptor = _make_descriptor(tmp_path, label=label)
    frozen_tokens = tuple(
        json.dumps(key, sort_keys=True, separators=(",", ":"))
        for key in ({"row": 0}, {"row": 1}, {"row": 2})
    )
    frozen_values = np.asarray(
        [1.0 + 0.5j, 2.0 - 0.25j, 3.0 + 0.75j], dtype=np.complex128
    )
    adapter = _LiveCanonicalAdapter(
        frozen_tokens,
        frozen_values,
        [{"row": 0}, {"row": 2}],
    )
    callback = make_live_canonical_roundtrip_callback(
        adapter,
        canonical_packets_for_vector=adapter.canonical_packets_for_vector,
        canonical_to_current_roundtrip_relative=(
            adapter.canonical_to_current_roundtrip_relative
        ),
        frozen_tokens=frozen_tokens,
        frozen_values=frozen_values,
    )
    return descriptor, callback


def _run_adapter_expectation(
    descriptor: dict[str, Any],
    callback: Any,
    action: Any,
    tmp_path: Path,
) -> None:
    load_and_condense_exact_rhs(
        descriptor,
        base_directory=tmp_path,
        action=action,
        canonical_roundtrip=callback,
        comm=MPI.COMM_SELF,
        expected_source_sha256=SOURCE_SHA,
        expected_input_sha256=HEX,
        expected_physical_model_sha256=HEX,
        expected_selected_manifest_sha256=HEX,
        expected_resolved_config_sha256=HEX,
        expected_operator_hash=HEX,
    )


def test_loader_adapter_preserves_builder_exception_and_cleans_active(
    tmp_path: Path,
) -> None:
    descriptor, callback = _adapter_descriptor_and_callback(tmp_path)
    action = _RaisingCondensedRhsAction()
    with pytest.raises(RuntimeError, match="builder sentinel"):
        _run_adapter_expectation(descriptor, callback, action, tmp_path)
    assert action.seen_active_rhs is not None
    assert not bool(action.seen_active_rhs)


@pytest.mark.parametrize(
    "action_type",
    [_InvalidTupleCondensedRhsAction, _InvalidMemberCondensedRhsAction],
)
def test_loader_adapter_cleans_vectors_from_invalid_builder_result(
    tmp_path: Path,
    action_type: type[_InvalidTupleCondensedRhsAction],
) -> None:
    descriptor, callback = _adapter_descriptor_and_callback(tmp_path)
    action = action_type()
    with pytest.raises(TypeError):
        _run_adapter_expectation(descriptor, callback, action, tmp_path)
    assert action.seen_active_rhs is not None
    assert not bool(action.seen_active_rhs)
    assert action.created
    assert all(not bool(vector) for vector in action.created)


def test_loader_rejects_conflicting_nested_identity_and_unsafe_route(tmp_path: Path) -> None:
    descriptor = _make_descriptor(tmp_path)
    conflicting = deepcopy(descriptor)
    conflicting["source_definition"]["input_sha256"] = "c" * 64
    with pytest.raises(ExactQualificationContractError, match="input_sha256"):
        validate_owner_vector_descriptor(conflicting)

    bad_schema = deepcopy(descriptor)
    bad_schema["schema"] = "wrong"
    with pytest.raises(ExactQualificationContractError, match="schema"):
        validate_owner_vector_descriptor(bad_schema)

    bad_side = deepcopy(descriptor)
    bad_side["side"] = "top"
    with pytest.raises(ExactQualificationContractError, match="side"):
        validate_owner_vector_descriptor(bad_side)

    bad_remap = deepcopy(descriptor)
    bad_remap["raw_global_row_remap"] = True
    with pytest.raises(ExactQualificationContractError, match="remapping"):
        validate_owner_vector_descriptor(bad_remap)


def test_loader_rejects_nonfinite_numeric_array(tmp_path: Path) -> None:
    descriptor = _make_descriptor(tmp_path)
    values = np.asarray([1.0 + 0.5j, np.nan + 0.0j, 3.0 + 0.75j])
    np.save(tmp_path / descriptor["array_path"], values, allow_pickle=False)
    descriptor["array_sha256"] = hash_array_bytes_sha256(values)
    descriptor["vector_identity"]["array_sha256"] = descriptor["array_sha256"]
    with pytest.raises(ExactQualificationContractError, match="nonfinite"):
        load_owner_local_vector(
            descriptor,
            base_directory=tmp_path,
            comm=MPI.COMM_SELF,
            canonical_roundtrip=_load_callback(
                [{"row": 0}, {"row": 2}], []
            ),
        )


def test_collective_loader_uses_owner_range_not_canonical_local_size(
    tmp_path: Path,
) -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("run this loader smoke with serial or MPI2")
    template = PETSc.Vec().createMPI((PETSc.DECIDE, 4), comm=comm)
    first, last = map(int, template.getOwnershipRange())
    owner_span = last - first
    rank_root = tmp_path / f"rank{comm.rank:04d}"
    canonical_keys = [
        {"row": first + offset} for offset in range(owner_span)
    ] + [{"row": 99 + comm.rank}]
    canonical_values = np.asarray(
        [10.0 + first + offset for offset in range(owner_span)]
        + [30.0 + comm.rank],
        dtype=np.complex128,
    )
    owner_values = np.asarray(canonical_values[:owner_span], dtype=np.complex128)
    canonical_hashes = comm.allgather(hash_array_bytes_sha256(canonical_values))
    global_sha256 = hashlib.sha256(
        "\n".join(canonical_hashes).encode("ascii")
    ).hexdigest()
    descriptor = _make_descriptor(
        rank_root,
        rank=comm.rank,
        mpi_size=comm.size,
        canonical_keys=canonical_keys,
        canonical_values=canonical_values,
        owner_values=owner_values,
        owner_range=(first, last),
        global_size=4,
        canonical_key_set_sha=HEX,
        global_sha256=global_sha256,
        label="distributed_rhs",
    )
    # The callback uses the live owner Vec and the rank's canonical key slice.
    seen: list[bool] = []
    try:
        vector, audit = load_owner_local_vector_collective(
            descriptor,
            base_directory=rank_root,
            template=template,
            comm=comm,
            canonical_roundtrip=_load_callback(
                canonical_keys[:owner_span], seen
            ),
        )
        assert seen == [True]
        assert audit["distributed"]["ownership_coverage_exact"] is True
        assert audit["distributed"]["global_sha256"] == global_sha256
        assert tuple(map(int, vector.getOwnershipRange())) == (first, last)
        vector.destroy()
    finally:
        template.destroy()


class _CopyRecovery:
    @staticmethod
    def build_full_state_from_condensed_solution(
        candidate: PETSc.Vec, _interior_rhs: Any
    ) -> tuple[PETSc.Vec, dict[str, Any]]:
        result = candidate.duplicate()
        candidate.copy(result)
        return result, {"temporary_rows": np.arange(candidate.getLocalSize())}


class _CombinedQualificationAction(_TinyCondensedRhsAction):
    @staticmethod
    def build_full_state_from_condensed_solution(
        candidate: PETSc.Vec,
        _interior_rhs: Any,
    ) -> tuple[PETSc.Vec, dict[str, Any]]:
        result = candidate.duplicate()
        candidate.copy(result)
        return result, {"temporary_rows": np.arange(candidate.getLocalSize())}


class _ThirdSourceFailAction(_CombinedQualificationAction):
    def __init__(self) -> None:
        super().__init__()
        self.recovery_calls = 0

    def build_full_state_from_condensed_solution(
        self,
        candidate: PETSc.Vec,
        interior_rhs: Any,
    ) -> tuple[PETSc.Vec, dict[str, Any]]:
        self.recovery_calls += 1
        result, audit = super().build_full_state_from_condensed_solution(
            candidate,
            interior_rhs,
        )
        if self.recovery_calls > 2:
            result.set(0.0)
            result.assemble()
        return result, audit


def test_exact_qualification_family_consumes_accepted_solution_and_is_json_safe(
    tmp_path: Path,
) -> None:
    first_descriptor, first_callback = _adapter_descriptor_and_callback(
        tmp_path,
        label="external_dtn_coupling",
    )
    second_descriptor, second_callback = _adapter_descriptor_and_callback(
        tmp_path,
        label="fixed_random_repeat_0",
    )
    matrix = _diagonal_matrix(
        2,
        MPI.COMM_SELF,
        diagonal_values=np.asarray([1.0, 1.0]),
    )
    accepted: list[tuple[str, bool, np.ndarray]] = []
    try:
        action = _CombinedQualificationAction()
        result = run_exact_qualification_family(
            {
                "external_dtn_coupling": first_descriptor,
                "fixed_random_repeat_0": second_descriptor,
            },
            base_directory=tmp_path,
            interface_operator=matrix,
            bare_operator=matrix,
            schur_action=action,
            canonical_roundtrip={
                "external_dtn_coupling": first_callback,
                "fixed_random_repeat_0": second_callback,
            },
            initial_labels=("external_dtn_coupling", "fixed_random_repeat_0"),
            mandatory_checkpoints=(1,),
            conditional_checkpoints=(),
            max_iterations=1,
            validation={
                "expected_source_sha256": SOURCE_SHA,
                "expected_input_sha256": HEX,
                "expected_physical_model_sha256": HEX,
                "expected_selected_manifest_sha256": HEX,
                "expected_resolved_config_sha256": HEX,
                "expected_operator_hash": HEX,
            },
            accepted_solution_callback=lambda label, _row, vector: accepted.append(
                (label, bool(vector), np.asarray(vector.array).copy())
            ),
        )
        assert result["initial_pair_gate_pass"] is True
        assert result["skipped_labels"] == []
        assert len(result["source_records"]) == 2
        assert all(record["full_residual_gate_pass"] for record in result["source_records"])
        assert all(record["fgmres"]["accepted_solution_present"] for record in result["source_records"])
        assert all(record["fgmres"]["accepted_solution_released_by_driver"] for record in result["source_records"])
        assert all(item[1] for item in accepted)
        json.dumps(result, sort_keys=True)
    finally:
        matrix.destroy()


def test_exact_qualification_family_rejects_label_swap(tmp_path: Path) -> None:
    descriptor, callback = _adapter_descriptor_and_callback(
        tmp_path,
        label="wrong_label",
    )
    matrix = _diagonal_matrix(2, MPI.COMM_SELF, diagonal_values=np.ones(2))
    try:
        with pytest.raises(ExactQualificationContractError, match="descriptor label"):
            run_exact_qualification_family(
                {
                    "external_dtn_coupling": descriptor,
                    "fixed_random_repeat_0": descriptor,
                },
                base_directory=tmp_path,
                interface_operator=matrix,
                bare_operator=matrix,
                schur_action=_CombinedQualificationAction(),
                canonical_roundtrip=callback,
                initial_labels=("external_dtn_coupling", "fixed_random_repeat_0"),
                mandatory_checkpoints=(1,),
                conditional_checkpoints=(),
                max_iterations=1,
            )
    finally:
        matrix.destroy()


def test_exact_qualification_family_does_not_ready_on_third_source_failure(
    tmp_path: Path,
) -> None:
    descriptors: dict[str, dict[str, Any]] = {}
    callbacks: dict[str, Any] = {}
    labels = (
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "third_source",
    )
    for label in labels:
        descriptors[label], callbacks[label] = _adapter_descriptor_and_callback(
            tmp_path,
            label=label,
        )
    matrix = _diagonal_matrix(2, MPI.COMM_SELF, diagonal_values=np.ones(2))
    try:
        result = run_exact_qualification_family(
            descriptors,
            base_directory=tmp_path,
            interface_operator=matrix,
            bare_operator=matrix,
            schur_action=_ThirdSourceFailAction(),
            canonical_roundtrip=callbacks,
            initial_labels=labels[:2],
            mandatory_checkpoints=(1,),
            conditional_checkpoints=(),
            max_iterations=1,
        )
        assert result["initial_pair_gate_pass"] is True
        assert result["all_sources_gate_pass"] is False
        assert result["classification"] == "V6_EXACT_QUALIFICATION_GATE_FAIL"
        assert result["status"] == "completed_all_sources_gate_negative"
        assert result["skipped_labels"] == []
        assert [record["label"] for record in result["source_records"]] == list(labels)
        json.dumps(result, sort_keys=True)
    finally:
        matrix.destroy()


def _diagonal_matrix(
    size: int,
    comm: MPI.Intracomm,
    diagonal_values: np.ndarray | None = None,
) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=1,
        comm=comm,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        value = row + 1 if diagonal_values is None else diagonal_values[row]
        matrix.setValue(row, row, PETSc.ScalarType(value))
    matrix.assemble()
    return matrix


def _fill_vector(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = map(int, vector.getOwnershipRange())
    vector.array[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()


def test_fgmres_nondivisor_restart_respects_checkpoint_boundary() -> None:
    comm = MPI.COMM_WORLD
    matrix = _diagonal_matrix(7, comm)
    active_rhs = matrix.createVecRight()
    condensed_rhs = matrix.createVecRight()
    values = np.asarray(
        [1.0 + 0.2j * index for index in range(7)], dtype=np.complex128
    )
    _fill_vector(active_rhs, values)
    _fill_vector(condensed_rhs, values)
    gate_calls: list[dict[str, Any]] = []
    try:
        result = run_exact_interface_fgmres(
            interface_operator=matrix,
            schur_action=_CopyRecovery(),
            bare_operator=matrix,
            condensed_rhs=condensed_rhs,
            active_rhs=active_rhs,
            interior_rhs_by_group={},
            right_preconditioner=None,
            label="synthetic",
            restart=3,
            mandatory_checkpoints=(1, 2, 4),
            conditional_checkpoints=(6,),
            authorize_conditional=lambda payload: (
                gate_calls.append(dict(payload)) or {"authorized": False}
            ),
            resource_callback=lambda: {"rss_bytes": 123},
            max_iterations=6,
        )
        assert _next_iteration_boundary(0, (16, 32, 64, 128), (256,), 512) == 128
        assert min(32, _next_iteration_boundary(0, (16, 32, 64, 128), (256,), 512)) == 32
        assert set(result["checkpoints"]) == {"1", "2", "4"}
        assert result["final_iteration"] == 4
        assert all(
            int(row["iteration"]) <= 4
            for row in result["checkpoint_history"]
        )
        assert len(gate_calls) == 1
        assert [row["iteration"] for row in gate_calls[0]["checkpoint_history"]] == [
            1,
            2,
            4,
        ]
        assert result["conditional_256_authorized"] is False
        assert result["active_rhs_unchanged"] is True
        assert result["condensed_rhs_unchanged"] is True
        assert result["numeric_allgather"] is False
        assert "6" not in result["checkpoints"]
        assert all(isinstance(row["recovery"], dict) for row in result["checkpoints"].values())
    finally:
        active_rhs.destroy()
        condensed_rhs.destroy()
        matrix.destroy()


def test_fgmres_returns_live_caller_owned_accepted_solution() -> None:
    matrix = _diagonal_matrix(
        2,
        MPI.COMM_SELF,
        diagonal_values=np.asarray([1.0, 1.0]),
    )
    active_rhs = matrix.createVecRight()
    condensed_rhs = matrix.createVecRight()
    _fill_vector(active_rhs, np.asarray([1.0 + 0.0j, 2.0 + 0.0j]))
    _fill_vector(condensed_rhs, np.asarray([1.0 + 0.0j, 2.0 + 0.0j]))
    callback_values: list[np.ndarray] = []
    accepted = None
    try:
        result = run_exact_interface_fgmres(
            interface_operator=matrix,
            schur_action=_CopyRecovery(),
            bare_operator=matrix,
            condensed_rhs=condensed_rhs,
            active_rhs=active_rhs,
            interior_rhs_by_group={},
            right_preconditioner=None,
            label="accepted",
            restart=2,
            mandatory_checkpoints=(1,),
            conditional_checkpoints=(),
            max_iterations=1,
            accepted_solution_callback=lambda _row, vector: callback_values.append(
                np.asarray(vector.array, dtype=np.complex128).copy()
            ),
        )
        accepted = result.pop("accepted_solution")
        assert accepted is not None
        assert result["accepted_solution_ownership"] == "caller_must_destroy"
        json.dumps(result, sort_keys=True)
        np.testing.assert_allclose(accepted.array, [1.0, 2.0])
        np.testing.assert_allclose(callback_values[0], accepted.array)
        assert result["active_rhs_unchanged"] is True
        assert result["condensed_rhs_unchanged"] is True
        assert all(
            not isinstance(value, np.ndarray)
            for value in result["checkpoints"]["1"]["recovery"].values()
        )
    finally:
        if accepted is not None:
            accepted.destroy()
        active_rhs.destroy()
        condensed_rhs.destroy()
        matrix.destroy()
