"""Tiny V6 exact-qualification loader and checkpoint-driver contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_exact_qualification import (
    ExactQualificationContractError,
    LoadedExactQualificationRHS,
    V5_VECTOR_SCHEMA,
    V5_VECTOR_SIDE,
    _collective_contract_call,
    canonical_values_roundtrip_error,
    hash_file_sha256,
    hash_array_bytes_sha256,
    aggregate_exact_packet_manifests,
    load_and_condense_exact_rhs,
    load_owner_local_vector,
    load_owner_local_vector_collective,
    make_live_canonical_roundtrip_callback,
    make_current_exact_packet_identity_provider,
    make_current_exact_solution_packet_consumer,
    make_current_exact_packet_writer,
    _normalize_packet_identity,
    rank_local_shard_binding_sha256,
    run_exact_qualification_family,
    run_exact_interface_fgmres,
    _next_iteration_boundary,
    validate_owner_vector_descriptor,
    write_current_exact_solution_packet,
)
from src.solvers.hybrid_bare_f_authority import gamma_values_for_vector
from src.solvers.hybrid_interface_packet_dolfinx import (
    build_gamma_canonical_layout,
    make_gamma_entity_block,
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
    ) -> tuple[tuple[str, ...], np.ndarray, dict[str, int]]:
        self.packet_calls += 1
        self.vector_alive.append(bool(vector))
        return (
            self.frozen_tokens,
            self.frozen_values.copy(),
            {"global_packet_count": int(vector.getSize())},
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


def test_loader_rejects_negative_roundtrip_relative(tmp_path: Path) -> None:
    descriptor = _make_descriptor(tmp_path)
    with pytest.raises(
        ExactQualificationContractError,
        match="outside tolerance",
    ):
        load_owner_local_vector(
            descriptor,
            base_directory=tmp_path,
            comm=MPI.COMM_SELF,
            canonical_roundtrip=lambda *_args: -1.0,
        )


def test_identity_hash_rejects_sign_prefixed_digest(tmp_path: Path) -> None:
    descriptor = _make_descriptor(tmp_path)
    descriptor["array_sha256"] = "-" + "a" * 63
    with pytest.raises(ExactQualificationContractError, match="array_sha256"):
        validate_owner_vector_descriptor(descriptor)


def test_owner_vector_rejects_negative_rhs_repeat_difference(tmp_path: Path) -> None:
    descriptor = _make_descriptor(tmp_path)
    descriptor["source_definition"]["rhs_repeat"]["relative_difference"] = -1.0e-15
    with pytest.raises(ExactQualificationContractError, match="repeat gate"):
        validate_owner_vector_descriptor(descriptor)


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


class _OffsetRecoveryAction(_CombinedQualificationAction):
    def __init__(self, offset: complex) -> None:
        super().__init__()
        self.offset = PETSc.ScalarType(offset)

    def build_full_state_from_condensed_solution(
        self,
        candidate: PETSc.Vec,
        interior_rhs: Any,
    ) -> tuple[PETSc.Vec, dict[str, Any]]:
        result, audit = super().build_full_state_from_condensed_solution(
            candidate,
            interior_rhs,
        )
        first, last = map(int, result.getOwnershipRange())
        if first <= 0 < last:
            result.array[0 - first] += self.offset
        return result, audit


class _PacketConsumerAction(_TinyCondensedRhsAction):
    def __init__(self, recovery_offset: complex = 0.0j) -> None:
        super().__init__()
        self.recovery_offset = PETSc.ScalarType(recovery_offset)

    def build_full_state_from_condensed_solution(
        self,
        _candidate: PETSc.Vec,
        _interior_rhs: Any,
    ) -> tuple[PETSc.Vec, dict[str, Any]]:
        full_state = PETSc.Vec().createMPI((3, 3), comm=MPI.COMM_SELF)
        full_state.array[:] = np.asarray(
            [
                1.0 + 0.5j,
                2.0 - 0.25j,
                3.0 + 0.75j,
            ],
            dtype=PETSc.ScalarType,
        )
        full_state.array[0] += self.recovery_offset
        full_state.assemble()
        return full_state, {"recovered_from": "group_back_substitution"}

    @staticmethod
    def extract_interface_from_active_vector(full_state: PETSc.Vec) -> PETSc.Vec:
        trace = PETSc.Vec().createMPI((2, 2), comm=MPI.COMM_SELF)
        trace.array[:] = np.asarray([4.0 + 0.0j, 5.0 + 0.0j], dtype=PETSc.ScalarType)
        trace.assemble()
        return trace

    @staticmethod
    def restrict_interface(trace: PETSc.Vec) -> tuple[PETSc.Vec, PETSc.Vec]:
        lower = PETSc.Vec().createMPI((2, 2), comm=MPI.COMM_SELF)
        upper = PETSc.Vec().createMPI((2, 2), comm=MPI.COMM_SELF)
        trace.copy(lower)
        trace.copy(upper)
        lower.assemble()
        upper.assemble()
        return lower, upper


class _DistributedPacketConsumerAction:
    def __init__(self, comm: MPI.Intracomm) -> None:
        self.comm = comm

    @staticmethod
    def build_full_state_from_condensed_solution(
        candidate: PETSc.Vec,
        _interior_rhs: Any,
    ) -> tuple[PETSc.Vec, dict[str, Any]]:
        full_state = candidate.duplicate()
        candidate.copy(full_state)
        return full_state, {"recovered_from": "distributed_tiny_fixture"}

    def extract_interface_from_active_vector(
        self,
        _full_state: PETSc.Vec,
    ) -> PETSc.Vec:
        trace = PETSc.Vec().createMPI(
            (PETSc.DECIDE, 2),
            comm=self.comm,
        )
        first, last = map(int, trace.getOwnershipRange())
        trace.array[:] = np.asarray(
            [4.0 + 0.0j, 5.0 + 0.0j],
            dtype=PETSc.ScalarType,
        )[first:last]
        trace.assemble()
        return trace

    @staticmethod
    def restrict_interface(trace: PETSc.Vec) -> tuple[PETSc.Vec, PETSc.Vec]:
        lower = trace.duplicate()
        upper = trace.duplicate()
        trace.copy(lower)
        trace.copy(upper)
        lower.assemble()
        upper.assemble()
        return lower, upper


def _tiny_gamma_layout(side: str) -> Any:
    transform = (
        np.asarray([[0.0 + 1.0j, 1.0], [-1.0, 0.0 - 0.5j]], dtype=np.complex128)
        if side == "lower"
        else np.asarray([[1.0 + 0.25j, 0.0], [0.0, -1.0 + 0.5j]], dtype=np.complex128)
    )
    block = make_gamma_entity_block(
        name=f"{side}_tiny_block",
        entity_dimension=1,
        physical_entity={"side": side, "entity": 0},
        raw_row_ids=(0, 1),
        canonical_to_raw=transform,
        orientation_state={"sign": -1 if side == "lower" else 1},
        floquet_master={"axis": "z", "side": side},
        floquet_coefficient=1.0 + 0.25j,
        canonical_key_records=(
            {"side": side, "channel": 0},
            {"side": side, "channel": 1},
        ),
    )
    return build_gamma_canonical_layout(
        (block,),
        (0, 1),
        plane_identity={"side": side, "fixture": "v6_exact_packet"},
        comm=MPI.COMM_SELF,
    )


def _tiny_gamma_layout_for_comm(side: str, comm: MPI.Intracomm) -> Any:
    rank = int(comm.rank)
    block = make_gamma_entity_block(
        name=f"{side}_distributed_tiny_block",
        entity_dimension=1,
        physical_entity={"side": side, "rank": rank},
        raw_row_ids=(0, 1),
        canonical_to_raw=np.asarray(
            [[0.0 + 1.0j, 1.0], [-1.0, 0.0 - 0.5j]],
            dtype=np.complex128,
        ),
        orientation_state={"rank": rank, "side": side},
        floquet_master={"axis": "z", "side": side, "rank": rank},
        floquet_coefficient=1.0 + 0.25j,
        canonical_key_records=(
            {"side": side, "rank": rank, "channel": 0},
            {"side": side, "rank": rank, "channel": 1},
        ),
    )
    return build_gamma_canonical_layout(
        (block,),
        (0, 1),
        plane_identity={"side": side, "fixture": "v6_distributed_packet"},
        comm=comm,
    )


def _writer_audit_with_paths(
    expected: dict[str, dict[str, Any]],
    arrays: dict[str, np.ndarray],
    tmp_path: Path,
    *,
    mutate: tuple[str, str] | None = None,
) -> dict[str, dict[str, Any]]:
    result = write_current_exact_solution_packet(
        root=tmp_path / "packet_artifacts",
        rank=int(expected["exact_output_canonical"]["rank"]),
        label=str(expected["exact_output_canonical"]["label"]),
        packet_values=arrays,
        packet_identities=expected,
        source_provenance=expected["exact_output_canonical"]["source_provenance"],
    )
    if mutate is not None:
        mutation, role_or_field = mutate
        if mutation in result:
            result[mutation][role_or_field] = "0" * 64
        elif mutation == "audit":
            result[role_or_field]["value_sha256"] = "0" * 64
        elif mutation == "missing_file":
            Path(result[role_or_field]["array_path"]).unlink()
        elif mutation == "array_bytes":
            path = Path(result[role_or_field]["array_path"])
            path.write_bytes(path.read_bytes() + b"tampered")
        elif mutation == "manifest_bytes":
            path = Path(result[role_or_field]["manifest_path"])
            path.write_bytes(path.read_bytes() + b"tampered")
        else:
            result[role_or_field][mutation] = "0" * 64
    return result


def _build_packet_consumer_fixture(
    tmp_path: Path,
    *,
    mutate: tuple[str, str] | None = None,
    exact_roundtrip: Any | None = None,
    recovery_offset: complex = 0.0j,
    full_residual_tolerance: float = 1.0e-9,
) -> tuple[Any, PETSc.Mat, PETSc.Vec, LoadedExactQualificationRHS]:
    descriptor = _make_descriptor(
        tmp_path,
        label="external_dtn_coupling",
        global_size=3,
        owner_range=(0, 3),
    )
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
        [{"row": 0}, {"row": 1}, {"row": 2}],
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
    action = _PacketConsumerAction(recovery_offset=recovery_offset)
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
    bare_operator = _diagonal_matrix(
        3,
        MPI.COMM_SELF,
        diagonal_values=np.ones(3),
    )
    lower_layout = _tiny_gamma_layout("lower")
    upper_layout = _tiny_gamma_layout("upper")
    identity_provider = make_current_exact_packet_identity_provider(
        lower_gamma_layout=lower_layout,
        upper_gamma_layout=upper_layout,
    )
    accepted = PETSc.Vec().createMPI((1, 1), comm=MPI.COMM_SELF)
    accepted.set(1.0)
    accepted.assemble()
    expected_holder: dict[str, Any] = {}

    def packet_callback(
        label: str,
        _checkpoint: dict[str, Any],
        vectors: dict[str, PETSc.Vec],
        packet_audit: dict[str, Any],
        canonical_packet: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        assert label == "external_dtn_coupling"
        assert "accepted_solution" not in vectors
        assert vectors["exact_output_active_state"].getSize() == 3
        assert vectors["gamma_lower_raw"].getSize() == 2
        assert vectors["gamma_upper_raw"].getSize() == 2
        assert vectors["gamma_lower_canonical"].dtype == np.dtype(np.complex128)
        assert vectors["gamma_upper_canonical"].dtype == np.dtype(np.complex128)
        for raw_key, canonical_key, role in (
            (
                "gamma_lower_raw",
                "gamma_lower_canonical",
                "gamma_l_canonical",
            ),
            (
                "gamma_upper_raw",
                "gamma_upper_canonical",
                "gamma_u_canonical",
            ),
        ):
            raw_hash = hash_array_bytes_sha256(
                np.asarray(vectors[raw_key].array, dtype=np.complex128)
            )
            canonical_hash = hash_array_bytes_sha256(vectors[canonical_key])
            assert canonical_hash == packet_audit[role]["value_sha256"]
            assert raw_hash != canonical_hash
        expected = identity_provider(
            label, vectors, packet_audit, canonical_packet
        )
        expected_holder["expected"] = expected
        assert expected["exact_output_canonical"]["global_active_size"] == 3
        assert expected["exact_output_canonical"]["rank"] == 0
        assert expected["exact_output_canonical"]["mpi_size"] == 1
        assert expected["exact_output_canonical"]["canonical_layout_sha256"] == (
            packet_audit["canonical_layout_sha256"]
        )
        assert expected["exact_output_canonical"]["canonical_key_set_sha256"] == (
            packet_audit["canonical_key_set_sha256"]
        )
        for role in (
            "exact_output_canonical",
            "exact_output_owner_rows",
            "gamma_l_canonical",
            "gamma_u_canonical",
        ):
            assert expected[role]["label"] == label
            assert expected[role]["rank"] == 0
            assert expected[role]["mpi_size"] == 1
            assert expected[role]["source_definition_sha256"] == (
                packet_audit["source_definition_sha256"]
            )
            assert expected[role]["bare_f_operator_hash"] == (
                packet_audit["bare_f_operator_hash"]
            )
            assert expected[role]["source_provenance"] == packet_audit[
                "source_provenance"
            ]
        assert expected["gamma_l_canonical"]["canonical_layout_sha256"] == (
            packet_audit["gamma_l_canonical"]["canonical_layout_sha256"]
        )
        assert expected["gamma_u_canonical"]["canonical_layout_sha256"] == (
            packet_audit["gamma_u_canonical"]["canonical_layout_sha256"]
        )
        arrays = {
            "exact_output_canonical": canonical_packet["values"],
            "exact_output_owner_rows": np.asarray(
                vectors["exact_output_active_state"].array,
                dtype=np.complex128,
            ).copy(),
            "gamma_l_canonical": np.asarray(
                vectors["gamma_lower_canonical"], dtype=np.complex128
            ).copy(),
            "gamma_u_canonical": np.asarray(
                vectors["gamma_upper_canonical"], dtype=np.complex128
            ).copy(),
        }
        if mutate is None:
            writer = make_current_exact_packet_writer(
                root=tmp_path / "packet_artifacts",
                rank=0,
            )
            return writer(label, _checkpoint, vectors, packet_audit, canonical_packet)
        return _writer_audit_with_paths(expected, arrays, tmp_path, mutate=mutate)

    consumer = make_current_exact_solution_packet_consumer(
        system=object(),
        schur_action=action,
        bare_operator=bare_operator,
        packet_callback=packet_callback,
        canonical_packets_for_vector=live_adapter.canonical_packets_for_vector,
        expected_packet_identity_provider=identity_provider,
        lower_gamma_layout=lower_layout,
        upper_gamma_layout=upper_layout,
        gamma_canonical_values_for_vector=gamma_values_for_vector,
        exact_output_canonical_roundtrip=(
            exact_roundtrip or live_adapter.canonical_to_current_roundtrip_relative
        ),
        full_residual_tolerance=full_residual_tolerance,
    )
    return consumer, bare_operator, accepted, bundle


def _build_distributed_packet_consumer_failure_fixture(
    comm: MPI.Intracomm,
    failure_mode: str,
) -> tuple[Any, PETSc.Mat, PETSc.Vec, LoadedExactQualificationRHS]:
    if failure_mode not in {"validation", "mutation"}:
        raise ValueError(f"unknown distributed packet failure mode: {failure_mode}")
    bare_operator = _diagonal_matrix(
        4,
        comm,
        diagonal_values=np.ones(4),
    )
    accepted = bare_operator.createVecRight()
    accepted.set(PETSc.ScalarType(1.0))
    accepted.assemble()
    active_rhs = bare_operator.createVecRight()
    accepted.copy(active_rhs)
    gamma_rhs = bare_operator.createVecRight()
    accepted.copy(gamma_rhs)
    condensed_rhs = bare_operator.createVecRight()
    accepted.copy(condensed_rhs)
    interior_rhs_by_group = {
        group: bare_operator.createVecRight() for group in range(3)
    }
    for vector in interior_rhs_by_group.values():
        accepted.copy(vector)

    first, last = map(int, active_rhs.getOwnershipRange())
    local_tokens = tuple(
        json.dumps(
            {"rank": int(comm.rank), "row": row},
            sort_keys=True,
            separators=(",", ":"),
        )
        for row in range(first, last)
    )
    local_order_sha = hashlib.sha256(
        "\n".join(local_tokens).encode("utf-8")
    ).hexdigest()
    local_set_sha = hashlib.sha256(
        "\n".join(sorted(local_tokens)).encode("utf-8")
    ).hexdigest()
    provenance = {
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "selected_manifest_sha256": HEX,
        "selected_identity_sha256": HEX,
        "resolved_config_sha256": HEX,
        "source_sha": SOURCE_SHA,
    }
    load_audit = {
        "canonical_key_order_sha256": local_order_sha,
        "canonical_key_set_local_sha256": local_set_sha,
        "source_provenance": provenance,
        "source_definition_sha256": SOURCE_DEFINITION_SHA,
        "bare_f_operator_hash": HEX,
        "canonical_layout_sha256": HEX,
        "canonical_key_set_sha256": HEX,
    }
    bundle = LoadedExactQualificationRHS(
        active_rhs=active_rhs,
        gamma_rhs=gamma_rhs,
        interior_rhs_by_group=interior_rhs_by_group,
        condensed_rhs=condensed_rhs,
        audit={"load": load_audit},
    )
    action = _DistributedPacketConsumerAction(comm)
    lower_layout = _tiny_gamma_layout_for_comm("lower", comm)
    upper_layout = _tiny_gamma_layout_for_comm("upper", comm)

    def live_packets(
        _system: Any,
        vector: PETSc.Vec,
    ) -> tuple[tuple[str, ...], np.ndarray, dict[str, int]]:
        values = np.asarray(
            [2.0 + 0.1 * row + 0.25j for row in range(first, last)],
            dtype=np.complex128,
        )
        if failure_mode == "mutation" and comm.rank == 0:
            vector.array[0] += PETSc.ScalarType(0.5 + 0.25j)
        if failure_mode == "validation" and comm.rank == 0:
            return ("{\"unexpected\":true}",), values, {
                "global_packet_count": 4
            }
        return local_tokens, values, {"global_packet_count": 4}

    def gamma_values(_vector: PETSc.Vec, layout: Any) -> np.ndarray:
        return np.asarray(
            [1.0 + 0.5j] * len(layout.canonical_keys),
            dtype=np.complex128,
        )

    consumer = make_current_exact_solution_packet_consumer(
        system=object(),
        schur_action=action,
        bare_operator=bare_operator,
        packet_callback=lambda *_args: {},
        canonical_packets_for_vector=live_packets,
        expected_packet_identity_provider=(
            make_current_exact_packet_identity_provider(
                lower_gamma_layout=lower_layout,
                upper_gamma_layout=upper_layout,
            )
        ),
        lower_gamma_layout=lower_layout,
        upper_gamma_layout=upper_layout,
        gamma_canonical_values_for_vector=gamma_values,
        exact_output_canonical_roundtrip=lambda *_args: 0.0,
    )
    return consumer, bare_operator, accepted, bundle


def test_packet_consumer_requires_four_live_hash_bound_roles(tmp_path: Path) -> None:
    consumer, bare_operator, accepted, bundle = _build_packet_consumer_fixture(tmp_path)
    try:
        result = consumer(
            "external_dtn_coupling",
            {"iteration": 1},
            accepted,
            bundle,
        )
        roles = result["packet_write"]
        assert set(roles) == {
            "exact_output_canonical",
            "exact_output_owner_rows",
            "gamma_l_canonical",
            "gamma_u_canonical",
        }
        assert result["packet_write"]["exact_output_owner_rows"]["local_size"] == 3
        assert result["packet_write"]["exact_output_canonical"][
            "canonical_key_count_local"
        ] == 3
        json.dumps(result, sort_keys=True)
    finally:
        accepted.destroy()
        bundle.destroy()
        bare_operator.destroy()


@pytest.mark.parametrize("failure_mode", ["validation", "mutation"])
def test_packet_consumer_collective_failure_keeps_mpi2_live(
    failure_mode: str,
) -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("run production consumer collective failure smoke with MPI2")
    consumer, bare_operator, accepted, bundle = (
        _build_distributed_packet_consumer_failure_fixture(comm, failure_mode)
    )
    caught: tuple[str, str] | None = None
    try:
        try:
            consumer(
                "distributed_failure",
                {"iteration": 1},
                accepted,
                bundle,
            )
        except ExactQualificationContractError as exc:
            caught = (type(exc).__name__, str(exc))
        assert caught is not None
        assert comm.allgather(caught) == [caught, caught]
        assert comm.allgather("consumer-after-failure") == [
            "consumer-after-failure",
            "consumer-after-failure",
        ]
    finally:
        bundle.destroy()
        accepted.destroy()
        bare_operator.destroy()


def test_packet_consumer_rejects_wrong_exact_output_roundtrip(
    tmp_path: Path,
) -> None:
    consumer, bare_operator, accepted, bundle = _build_packet_consumer_fixture(
        tmp_path,
        exact_roundtrip=lambda *_args: 1.0e-6,
    )
    try:
        with pytest.raises(
            ExactQualificationContractError,
            match="exact-output canonical roundtrip",
        ):
            consumer(
                "external_dtn_coupling",
                {"iteration": 1},
                accepted,
                bundle,
            )
    finally:
        accepted.destroy()
        bundle.destroy()
        bare_operator.destroy()


def test_packet_consumer_rejects_negative_exact_output_roundtrip(
    tmp_path: Path,
) -> None:
    consumer, bare_operator, accepted, bundle = _build_packet_consumer_fixture(
        tmp_path,
        exact_roundtrip=lambda *_args: -1.0e-15,
    )
    try:
        with pytest.raises(
            ExactQualificationContractError,
            match="exact-output canonical roundtrip",
        ):
            consumer(
                "external_dtn_coupling",
                {"iteration": 1},
                accepted,
                bundle,
            )
    finally:
        accepted.destroy()
        bundle.destroy()
        bare_operator.destroy()


@pytest.mark.parametrize(
    "mutate",
    [
        ("exact_output_canonical", "value_sha256"),
        ("gamma_l_canonical", "source_definition_sha256"),
    ],
)
def test_packet_consumer_rejects_writer_identity_mismatch(
    tmp_path: Path,
    mutate: tuple[str, str],
) -> None:
    consumer, bare_operator, accepted, bundle = _build_packet_consumer_fixture(
        tmp_path,
        mutate=mutate,
    )
    try:
        with pytest.raises(ValueError, match="differs from expected identity"):
            consumer(
                "external_dtn_coupling",
                {"iteration": 1},
                accepted,
                bundle,
            )
    finally:
        accepted.destroy()
        bundle.destroy()
        bare_operator.destroy()


def _fake_packet_write_roles(label: str) -> dict[str, dict[str, Any]]:
    return {
        role: {
            "label": label,
            "local_size": 1,
            "global_size": 1,
            "value_sha256": HEX,
            "canonical_key_order_sha256": HEX,
            "canonical_key_set_sha256": HEX,
            "source_definition_sha256": SOURCE_DEFINITION_SHA,
            "bare_f_operator_hash": HEX,
            "shard_sha256": HEX,
            "metadata_sha256": HEX,
            "manifest_sha256": HEX,
            "array_sha256": HEX,
            "ownership_range": [0, 1],
            "owner_row_order": "petsc_current_ownership_range",
            "path": str(Path("missing") / f"{role}.json"),
            "array_path": str(Path("missing") / f"{role}.npy"),
            "manifest_path": str(Path("missing") / f"{role}.manifest.json"),
        }
        for role in (
            "exact_output_canonical",
            "exact_output_owner_rows",
            "gamma_l_canonical",
            "gamma_u_canonical",
        )
    }


@pytest.mark.parametrize("shape", ["empty", "one_role", "fake_hash_bound"])
def test_family_packetization_gate_rejects_incomplete_or_fake_writer(
    tmp_path: Path,
    shape: str,
) -> None:
    labels = ("external_dtn_coupling", "fixed_random_repeat_0")
    descriptors: dict[str, dict[str, Any]] = {}
    callbacks: dict[str, Any] = {}
    for label in labels:
        descriptors[label], callbacks[label] = _adapter_descriptor_and_callback(
            tmp_path,
            label=label,
        )
    matrix = _diagonal_matrix(2, MPI.COMM_SELF, diagonal_values=np.ones(2))
    called_labels: list[str] = []

    def consumer(
        label: str,
        _row: dict[str, Any],
        _accepted: PETSc.Vec,
        _bundle: LoadedExactQualificationRHS,
    ) -> dict[str, Any]:
        called_labels.append(label)
        roles = _fake_packet_write_roles(label)
        if shape == "empty":
            roles = {}
        elif shape == "one_role":
            roles = {"exact_output_canonical": roles["exact_output_canonical"]}
        return {"packet_write": roles}

    try:
        with pytest.raises(
            ExactQualificationContractError,
            match="packetization contract",
        ):
            run_exact_qualification_family(
                descriptors,
                base_directory=tmp_path,
                interface_operator=matrix,
                bare_operator=matrix,
                schur_action=_CombinedQualificationAction(),
                canonical_roundtrip=callbacks,
                initial_labels=labels,
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
                accepted_solution_consumer=consumer,
            )
        assert called_labels == [labels[0]]
    finally:
        matrix.destroy()


def test_family_packetization_failure_is_collective_and_stops_remaining_sources(
    tmp_path: Path,
) -> None:
    """Exercise the family driver, not only its packet helper, under MPI2."""

    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("run family packetization liveness smoke with MPI2")
    labels = (
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "third_source",
    )
    global_size = 4
    template = PETSc.Vec().createMPI((PETSc.DECIDE, global_size), comm=comm)
    first, last = map(int, template.getOwnershipRange())
    rank_root = tmp_path / f"family-rank{comm.rank:04d}"
    global_key_set_sha = _key_set_sha(
        [{"row": index} for index in range(global_size)]
    )
    descriptors: dict[str, dict[str, Any]] = {}
    callbacks: dict[str, Any] = {}
    for label_index, label in enumerate(labels):
        local_values = np.asarray(
            [
                1.0 + label_index + row + 0.125j * (comm.rank + 1)
                for row in range(first, last)
            ],
            dtype=np.complex128,
        )
        global_value_hash = hashlib.sha256(
            "\n".join(
                comm.allgather(hash_array_bytes_sha256(local_values))
            ).encode("ascii")
        ).hexdigest()
        descriptor_root = rank_root / label
        canonical_keys = [{"row": row} for row in range(first, last)]
        descriptor = _make_descriptor(
            descriptor_root,
            rank=comm.rank,
            mpi_size=comm.size,
            label=label,
            global_size=global_size,
            owner_range=(first, last),
            canonical_keys=canonical_keys,
            canonical_values=local_values,
            owner_values=local_values,
            canonical_key_set_sha=global_key_set_sha,
            global_sha256=global_value_hash,
        )
        for field in (
            "array_path",
            "owner_row_array_path",
            "canonical_layout_path",
        ):
            descriptor[field] = f"{label}/{descriptor[field]}"
        descriptors[label] = descriptor
        callbacks[label] = _load_callback(canonical_keys, [])

    matrix = _diagonal_matrix(
        global_size,
        comm,
        diagonal_values=np.ones(global_size),
    )
    called_labels: list[str] = []

    def consumer(
        label: str,
        _row: Mapping[str, Any],
        _accepted: PETSc.Vec,
        _bundle: LoadedExactQualificationRHS,
    ) -> Mapping[str, Any]:
        called_labels.append(label)
        if comm.rank == 0:
            raise ExactQualificationContractError(
                "rank0 injected family packet audit failure"
            )
        return {"packet_write": {}}

    caught: tuple[str, str] | None = None
    try:
        try:
            run_exact_qualification_family(
                descriptors,
                base_directory=rank_root,
                interface_operator=matrix,
                bare_operator=matrix,
                schur_action=_CombinedQualificationAction(),
                canonical_roundtrip=callbacks,
                initial_labels=labels[:2],
                mandatory_checkpoints=(1,),
                conditional_checkpoints=(),
                max_iterations=1,
                accepted_solution_consumer=consumer,
            )
        except ExactQualificationContractError as exc:
            caught = (type(exc).__name__, str(exc))
        assert caught is not None
        assert comm.allgather(caught) == [caught, caught]
        assert comm.allgather(called_labels) == [
            [labels[0]],
            [labels[0]],
        ]
        assert comm.allgather("family-after-packet-failure") == [
            "family-after-packet-failure",
            "family-after-packet-failure",
        ]
    finally:
        matrix.destroy()
        template.destroy()


@pytest.mark.parametrize(
    "mutate",
    [
        ("missing_file", "exact_output_owner_rows"),
        ("array_bytes", "gamma_u_canonical"),
        ("manifest_bytes", "gamma_l_canonical"),
        ("exact_output_owner_rows", "canonical_key_set_sha256"),
        ("exact_output_owner_rows", "bare_f_operator_hash"),
        ("gamma_u_canonical", "shard_sha256"),
    ],
)
def test_packet_consumer_rejects_file_and_identity_tampering(
    tmp_path: Path,
    mutate: tuple[str, str],
) -> None:
    consumer, bare_operator, accepted, bundle = _build_packet_consumer_fixture(
        tmp_path,
        mutate=mutate,
    )
    try:
        with pytest.raises(ValueError):
            consumer(
                "external_dtn_coupling",
                {"iteration": 1},
                accepted,
                bundle,
            )
    finally:
        accepted.destroy()
        bundle.destroy()
        bare_operator.destroy()


def _aggregate_packet_fixture_identities(
    *,
    comm: MPI.Intracomm,
    label: str,
    canonical_count: int,
    owner_range: tuple[int, int],
    global_size: int,
    canonical_key_set_sha256: str,
    canonical_key_order_sha256: str,
    canonical_key_set_local_sha256: str,
    source_provenance: dict[str, str],
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, Any]]]:
    source_definition = SOURCE_DEFINITION_SHA
    bare_operator = HEX
    exact_layout = "d" * 64
    lower_layout = "e" * 64
    upper_layout = "f" * 64
    rank = int(comm.rank)
    mpi_size = int(comm.size)
    owner_start, owner_end = owner_range
    owner_count = owner_end - owner_start
    base = 1.0 + 0.25j * rank
    arrays = {
        "exact_output_canonical": np.asarray(
            [base + index for index in range(canonical_count)],
            dtype=np.complex128,
        ),
        "exact_output_owner_rows": np.asarray(
            [base + 10.0 + index for index in range(owner_count)],
            dtype=np.complex128,
        ),
        "gamma_l_canonical": np.asarray(
            [base + 20.0 + index for index in range(canonical_count)],
            dtype=np.complex128,
        ),
        "gamma_u_canonical": np.asarray(
            [base + 30.0 + index for index in range(canonical_count)],
            dtype=np.complex128,
        ),
    }

    def common(role: str, value_sha256: str, layout_sha256: str) -> dict[str, Any]:
        return {
            "label": label,
            "role": role,
            "dtype": "complex128",
            "rank": rank,
            "mpi_size": mpi_size,
            "value_sha256": value_sha256,
            "source_definition_sha256": source_definition,
            "bare_f_operator_hash": bare_operator,
            "canonical_layout_sha256": layout_sha256,
            "canonical_key_set_sha256": canonical_key_set_sha256,
            "source_provenance": deepcopy(source_provenance),
        }

    identities: dict[str, dict[str, Any]] = {
        "exact_output_canonical": {
            **common(
                "exact_output_canonical",
                hash_array_bytes_sha256(arrays["exact_output_canonical"]),
                exact_layout,
            ),
            "canonical_key_count_local": canonical_count,
            "global_active_size": global_size,
            "canonical_key_order_sha256": canonical_key_order_sha256,
            "canonical_key_set_local_sha256": canonical_key_set_local_sha256,
            "canonical_roundtrip_relative": 0.0,
        },
        "exact_output_owner_rows": {
            **common(
                "exact_output_owner_rows",
                hash_array_bytes_sha256(arrays["exact_output_owner_rows"]),
                exact_layout,
            ),
            "local_size": owner_count,
            "global_size": global_size,
            "ownership_range": [owner_start, owner_end],
            "owner_row_order": "petsc_current_ownership_range",
        },
    }
    for role, layout_sha256 in (
        ("gamma_l_canonical", lower_layout),
        ("gamma_u_canonical", upper_layout),
    ):
        values = arrays[role]
        identities[role] = {
            **common(role, hash_array_bytes_sha256(values), layout_sha256),
            "canonical_key_count_local": canonical_count,
            "canonical_global_size": global_size,
            "canonical_key_order_sha256": canonical_key_order_sha256,
            "canonical_key_set_local_sha256": canonical_key_set_local_sha256,
            "gamma_transform_sha256": hashlib.sha256(
                f"{role}:nontrivial-transform".encode("ascii")
            ).hexdigest(),
        }
    return arrays, identities


def test_production_packet_writer_and_aggregate_handles_uneven_canonical_shards(
    tmp_path: Path,
) -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("run packet aggregate smoke with serial or MPI2")
    template = PETSc.Vec().createMPI((PETSc.DECIDE, 4), comm=comm)
    owner_range = tuple(map(int, template.getOwnershipRange()))
    if comm.size == 1:
        canonical_indices = tuple(range(4))
    elif comm.rank == 0:
        canonical_indices = (0,)
    else:
        canonical_indices = (1, 2, 3)
    all_tokens = tuple(
        json.dumps({"channel": index}, sort_keys=True, separators=(",", ":"))
        for index in range(4)
    )
    local_tokens = tuple(all_tokens[index] for index in canonical_indices)
    global_key_set_sha256 = hashlib.sha256(
        "\n".join(sorted(all_tokens)).encode("utf-8")
    ).hexdigest()
    local_order_sha256 = hashlib.sha256(
        "\n".join(local_tokens).encode("utf-8")
    ).hexdigest()
    local_set_sha256 = hashlib.sha256(
        "\n".join(sorted(local_tokens)).encode("utf-8")
    ).hexdigest()
    provenance = {
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "selected_manifest_sha256": HEX,
        "selected_identity_sha256": HEX,
        "resolved_config_sha256": HEX,
        "source_sha": SOURCE_SHA,
    }
    arrays, identities = _aggregate_packet_fixture_identities(
        comm=comm,
        label="aggregate_smoke",
        canonical_count=len(canonical_indices),
        owner_range=owner_range,
        global_size=4,
        canonical_key_set_sha256=global_key_set_sha256,
        canonical_key_order_sha256=local_order_sha256,
        canonical_key_set_local_sha256=local_set_sha256,
        source_provenance=provenance,
    )
    output_root = tmp_path / "aggregate_packets"
    forbidden_root = tmp_path / "frozen_v5_root"
    descriptor_metadata_hashes = {
        source_label: f"{comm.rank + 1:064x}"
        for source_label in (
            "external_dtn_coupling",
            "fixed_random_repeat_0",
            "modal_traction_positive",
            "modal_traction_negative",
            "fixed_random_repeat_1",
        )
    }
    try:
        local_packets = write_current_exact_solution_packet(
            root=output_root,
            rank=comm.rank,
            label="aggregate_smoke",
            packet_values=arrays,
            packet_identities=identities,
            source_provenance=provenance,
            forbidden_root=forbidden_root,
        )
        aggregate = aggregate_exact_packet_manifests(
            local_packets,
            root=output_root,
            label="aggregate_smoke",
            comm=comm,
            source_provenance=provenance,
            qualification_source_provenance={
                **provenance,
                "source_sha": "d" * 40,
            },
            frozen_rhs_descriptor_metadata_sha256=descriptor_metadata_hashes,
            expected_gamma_global_sizes={
                "gamma_l_canonical": 4,
                "gamma_u_canonical": 4,
            },
            forbidden_root=forbidden_root,
        )
        assert aggregate["schema"] == (
            "task040.v6.current_exact_packet_rank_manifest.v1"
        )
        assert aggregate["mpi_size"] == comm.size
        assert aggregate["rank_count"] == comm.size
        assert aggregate["role_count"] == 4
        assert aggregate["role_count_per_rank"] == 4
        assert aggregate["source_provenance"] == provenance
        assert aggregate["qualification_source_provenance"] == {
            **provenance,
            "source_sha": "d" * 40,
        }
        assert aggregate["bare_f_operator_hash"] == HEX
        assert aggregate["numeric_allgather"] is False
        assert aggregate["full_numeric_replica"] is False
        assert aggregate["frozen_rhs_descriptor_metadata_sha256_by_rank"][
            comm.rank
        ] == descriptor_metadata_hashes
        assert len(
            set(
                json.dumps(item, sort_keys=True)
                for item in aggregate[
                    "frozen_rhs_descriptor_metadata_sha256_by_rank"
                ]
            )
        ) == (1 if comm.size == 1 else comm.size)
        assert len(aggregate["frozen_rhs_descriptor_metadata_binding_sha256"]) == 64
        aggregate_payload = json.loads(Path(aggregate["path"]).read_text())
        assert aggregate_payload["schema"] == aggregate["schema"]
        assert aggregate_payload["rank_count"] == comm.size
        assert aggregate_payload["role_count"] == 4
        assert aggregate_payload["role_count_per_rank"] == 4
        assert aggregate_payload["source_provenance"] == provenance
        assert aggregate_payload["bare_f_operator_hash"] == HEX
        assert aggregate_payload["numeric_allgather"] is False
        assert aggregate_payload["full_numeric_replica"] is False
        assert len(aggregate_payload["rank_manifests"]) == comm.size
        assert hash_file_sha256(Path(aggregate["path"])) == aggregate["sha256"]
        assert identities["gamma_l_canonical"]["gamma_transform_sha256"] != HEX
        comm.Barrier()
        if comm.rank == 0:
            tampered = Path(local_packets["gamma_l_canonical"]["array_path"])
            tampered.write_bytes(tampered.read_bytes() + b"tampered")
        comm.Barrier()
        with pytest.raises(ExactQualificationContractError, match="packet"):
            aggregate_exact_packet_manifests(
                local_packets,
                root=output_root,
                label="aggregate_smoke",
                comm=comm,
                source_provenance=provenance,
                qualification_source_provenance={
                    **provenance,
                    "source_sha": "d" * 40,
                },
                frozen_rhs_descriptor_metadata_sha256=descriptor_metadata_hashes,
                expected_gamma_global_sizes={
                    "gamma_l_canonical": 4,
                    "gamma_u_canonical": 4,
                },
                forbidden_root=forbidden_root,
            )
        assert comm.allgather("post-tamper-collective") == [
            "post-tamper-collective"
        ] * comm.size
    finally:
        template.destroy()


def test_production_packet_writer_propagates_one_rank_failure_and_stays_live(
    tmp_path: Path,
) -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("run writer failure smoke with MPI2")
    template = PETSc.Vec().createMPI((PETSc.DECIDE, 4), comm=comm)
    owner_range = tuple(map(int, template.getOwnershipRange()))
    canonical_indices = (0,) if comm.rank == 0 else (1, 2, 3)
    all_tokens = tuple(
        json.dumps({"channel": index}, sort_keys=True, separators=(",", ":"))
        for index in range(4)
    )
    local_tokens = tuple(all_tokens[index] for index in canonical_indices)
    global_key_set_sha256 = hashlib.sha256(
        "\n".join(sorted(all_tokens)).encode("utf-8")
    ).hexdigest()
    local_order_sha256 = hashlib.sha256(
        "\n".join(local_tokens).encode("utf-8")
    ).hexdigest()
    local_set_sha256 = hashlib.sha256(
        "\n".join(sorted(local_tokens)).encode("utf-8")
    ).hexdigest()
    provenance = {
        "input_sha256": HEX,
        "physical_model_sha256": HEX,
        "selected_manifest_sha256": HEX,
        "selected_identity_sha256": HEX,
        "resolved_config_sha256": HEX,
        "source_sha": SOURCE_SHA,
    }
    arrays, identities = _aggregate_packet_fixture_identities(
        comm=comm,
        label="writer_failure",
        canonical_count=len(canonical_indices),
        owner_range=owner_range,
        global_size=4,
        canonical_key_set_sha256=global_key_set_sha256,
        canonical_key_order_sha256=local_order_sha256,
        canonical_key_set_local_sha256=local_set_sha256,
        source_provenance=provenance,
    )
    template.array[:] = arrays["exact_output_owner_rows"]
    template.assemble()
    packet_audit: dict[str, Any] = {
        "source_provenance": provenance,
        **deepcopy(identities),
    }
    if comm.rank == 0:
        packet_audit["gamma_l_canonical"]["value_sha256"] = "0" * 64
    writer = make_current_exact_packet_writer(
        root=tmp_path / "writer_failure_packets",
        rank=comm.rank,
    )
    try:
        with pytest.raises(
            ExactQualificationContractError,
            match="collective exact packet writer failed",
        ):
            writer(
                "writer_failure",
                {"iteration": 1},
                {
                    "exact_output_active_state": template,
                    "gamma_lower_canonical": arrays["gamma_l_canonical"],
                    "gamma_upper_canonical": arrays["gamma_u_canonical"],
                },
                packet_audit,
                {"tokens": local_tokens, "values": arrays["exact_output_canonical"]},
            )
        assert comm.allgather("writer-failure-liveness") == [
            "writer-failure-liveness",
            "writer-failure-liveness",
        ]
    finally:
        template.destroy()


@pytest.mark.parametrize(
    "stage",
    [
        "live canonical identity",
        "exact-output roundtrip",
        "packet writer",
    ],
)
def test_collective_packet_contract_propagates_one_rank_failure(
    stage: str,
) -> None:
    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("run collective packet failure smoke with MPI2")

    def failing_stage() -> None:
        if comm.rank == 0:
            raise ValueError("rank0 injected packet contract failure")

    with pytest.raises(ExactQualificationContractError, match="rank0 injected"):
        _collective_contract_call(comm, stage, failing_stage)
    assert comm.allgather("packet-contract-alive") == [
        "packet-contract-alive",
        "packet-contract-alive",
    ]


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
            packetization_required=False,
        )
        assert result["initial_pair_gate_pass"] is True
        assert result["skipped_labels"] == []
        assert len(result["source_records"]) == 2
        assert all(record["full_residual_gate_pass"] for record in result["source_records"])
        assert all(record["fgmres"]["accepted_solution_present"] for record in result["source_records"])
        assert all(record["fgmres"]["accepted_solution_released_by_driver"] for record in result["source_records"])
        assert all(
            record["adapter"]["retained_during_callbacks"] is True
            and record["adapter"]["released_by_driver"] is True
            and record["adapter"]["destroyed_after_source"] is True
            for record in result["source_records"]
        )
        assert all(item[1] for item in accepted)
        json.dumps(result, sort_keys=True)
    finally:
        matrix.destroy()


def test_nondefault_full_residual_tolerance_controls_solver_and_family(
    tmp_path: Path,
) -> None:
    descriptors: dict[str, dict[str, Any]] = {}
    callbacks: dict[str, Any] = {}
    labels = ("external_dtn_coupling", "fixed_random_repeat_0")
    for label in labels:
        descriptors[label], callbacks[label] = _adapter_descriptor_and_callback(
            tmp_path,
            label=label,
        )
    matrix = _diagonal_matrix(2, MPI.COMM_SELF, diagonal_values=np.ones(2))
    strict_consumer_calls: list[str] = []
    loose_consumer_calls: list[str] = []

    def run_with_tolerance(
        tolerance: float,
        calls: list[str],
    ) -> dict[str, Any]:
        return run_exact_qualification_family(
            descriptors,
            base_directory=tmp_path,
            interface_operator=matrix,
            bare_operator=matrix,
            schur_action=_OffsetRecoveryAction(1.0e-6 + 0.0j),
            canonical_roundtrip=callbacks,
            initial_labels=labels,
            mandatory_checkpoints=(1,),
            conditional_checkpoints=(),
            max_iterations=1,
            accepted_solution_consumer=(
                lambda label, _row, _accepted, _bundle: (
                    calls.append(label) or {"packet_write": {}}
                )
            ),
            packetization_required=False,
            full_residual_tolerance=tolerance,
        )

    try:
        strict = run_with_tolerance(2.0e-7, strict_consumer_calls)
        loose = run_with_tolerance(4.0e-7, loose_consumer_calls)
        strict_records = strict["source_records"]
        loose_records = loose["source_records"]
        assert all(
            float(record["best_full_true_residual_relative"]) > 2.0e-7
            for record in strict_records
        )
        assert all(
            float(record["best_full_true_residual_relative"]) <= 4.0e-7
            for record in loose_records
        )
        assert all(
            record["fgmres"]["full_residual_tolerance"] == 2.0e-7
            for record in strict_records
        )
        assert all(
            record["fgmres"]["full_residual_tolerance"] == 4.0e-7
            for record in loose_records
        )
        assert strict["all_sources_gate_pass"] is False
        assert loose["all_sources_gate_pass"] is True
        assert strict_consumer_calls == []
        assert loose_consumer_calls == list(labels)
        assert all(
            record["packetization_gate_pass"] is True
            and record["fgmres"]["accepted_solution_consumed"] is True
            for record in loose_records
        )
    finally:
        matrix.destroy()


def test_nondefault_full_residual_tolerance_controls_production_packet_consumer(
    tmp_path: Path,
) -> None:
    """The production packet bridge must use the caller's residual threshold."""

    strict_consumer, strict_operator, strict_accepted, strict_bundle = (
        _build_packet_consumer_fixture(
            tmp_path / "strict",
            recovery_offset=1.0e-6 + 0.0j,
            full_residual_tolerance=2.0e-7,
            exact_roundtrip=lambda *_args: 0.0,
        )
    )
    loose_consumer, loose_operator, loose_accepted, loose_bundle = (
        _build_packet_consumer_fixture(
            tmp_path / "loose",
            recovery_offset=1.0e-6 + 0.0j,
            full_residual_tolerance=4.0e-7,
            exact_roundtrip=lambda *_args: 0.0,
        )
    )
    try:
        loose_result = loose_consumer(
            "external_dtn_coupling",
            {"iteration": 1},
            loose_accepted,
            loose_bundle,
        )
        loose_relative = float(loose_result["full_residual_relative"])
        assert 2.0e-7 < loose_relative <= 4.0e-7
        assert loose_result["full_residual_tolerance"] == 4.0e-7
        assert set(loose_result["packet_write"]) == {
            "exact_output_canonical",
            "exact_output_owner_rows",
            "gamma_l_canonical",
            "gamma_u_canonical",
        }
        with pytest.raises(ValueError, match="full residual exceeds tolerance"):
            strict_consumer(
                "external_dtn_coupling",
                {"iteration": 1},
                strict_accepted,
                strict_bundle,
            )
    finally:
        strict_accepted.destroy()
        strict_bundle.destroy()
        strict_operator.destroy()
        loose_accepted.destroy()
        loose_bundle.destroy()
        loose_operator.destroy()


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
            packetization_required=False,
        )
        assert result["initial_pair_gate_pass"] is True
        assert result["all_sources_gate_pass"] is False
        assert result["classification"] == "V6_EXACT_QUALIFICATION_GATE_FAIL"
        assert result["status"] == (
            "completed_exact_numerical_gate_negative_continuation_allowed"
        )
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


def _cyclic_shift_matrix(size: int, comm: MPI.Intracomm) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=2,
        comm=comm,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValue(row, row, PETSc.ScalarType(2.0))
        matrix.setValue(
            row,
            (row + 1) % size,
            PETSc.ScalarType(0.25 + 0.05j),
        )
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


def test_fgmres_reports_nonrequested_early_final_iteration() -> None:
    """An Arnoldi happy breakdown is reported even without a requested point."""

    matrix = _diagonal_matrix(
        2,
        MPI.COMM_SELF,
        diagonal_values=np.asarray([1.0, 1.0]),
    )
    active_rhs = matrix.createVecRight()
    condensed_rhs = matrix.createVecRight()
    _fill_vector(active_rhs, np.asarray([1.0 + 0.0j, 2.0 + 0.0j]))
    _fill_vector(condensed_rhs, np.asarray([1.0 + 0.0j, 2.0 + 0.0j]))
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
            label="early-final",
            restart=3,
            mandatory_checkpoints=(4,),
            conditional_checkpoints=(),
            max_iterations=4,
        )
        accepted = result.pop("accepted_solution")
        assert accepted is not None
        assert result["checkpoints"] == {}
        assert result["early_final_record"]["iteration"] == 1
        assert result["checkpoint_history"][0]["checkpoint_kind"] == "early_final"
        assert result["final_iteration"] == 1
        assert result["stopped_at_happy_breakdown"] is True
        json.dumps(result, sort_keys=True)
    finally:
        if accepted is not None:
            accepted.destroy()
        active_rhs.destroy()
        condensed_rhs.destroy()
        matrix.destroy()


def test_fgmres_checkpoint_records_solution_and_hessenberg_diagnostics() -> None:
    matrix = _diagonal_matrix(
        2,
        MPI.COMM_SELF,
        diagonal_values=np.asarray([1.0, 1.0]),
    )
    active_rhs = matrix.createVecRight()
    condensed_rhs = matrix.createVecRight()
    residual = matrix.createVecLeft()
    _fill_vector(active_rhs, np.asarray([1.0 + 0.0j, 2.0 + 0.0j]))
    _fill_vector(condensed_rhs, np.asarray([1.0 + 0.0j, 2.0 + 0.0j]))
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
            label="checkpoint-diagnostics",
            mandatory_checkpoints=(1,),
            conditional_checkpoints=(),
            max_iterations=1,
        )
        record = result["checkpoints"]["1"]
        for name in (
            "interface_solution_norm",
            "recovered_full_solution_norm",
            "small_hessenberg_projected_residual_absolute",
            "small_hessenberg_projected_residual_relative",
            "small_hessenberg_reported_residual_absolute",
            "small_hessenberg_reported_residual_relative",
        ):
            assert np.isfinite(record[name])
        assert record["small_hessenberg_projected_residual_absolute"] == pytest.approx(
            record["small_hessenberg_reported_residual_absolute"]
        )
        assert record["reported_residual_kind"] == "projected_least_squares_alias"
        assert record["small_hessenberg_relative_denominator_kind"] == (
            "original_interface_rhs_norm"
        )
        assert record["small_hessenberg_relative_denominator"] == pytest.approx(
            float(condensed_rhs.norm())
        )
        assert record["small_hessenberg_projected_residual_absolute"] >= 0.0
        assert record["small_hessenberg_projected_residual_relative"] >= 0.0
        accepted = result.pop("accepted_solution")
        matrix.mult(accepted, residual)
        residual.axpy(PETSc.ScalarType(-1.0), active_rhs)
        assert record["full_true_residual_norm"] == pytest.approx(
            float(residual.norm())
        )
    finally:
        if accepted is not None:
            accepted.destroy()
        residual.destroy()
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


@pytest.mark.parametrize("failure_mode", ["rank_skew", "callback_exception"])
def test_fgmres_conditional_decision_is_collective_mpi2(
    failure_mode: str,
) -> None:
    """Conditional extension cannot diverge while other ranks enter PETSc."""

    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("run conditional-decision liveness smoke with MPI2")
    matrix = _cyclic_shift_matrix(129, comm)
    active_rhs = matrix.createVecRight()
    condensed_rhs = matrix.createVecRight()
    values = np.asarray(
        [1.0 + 0.1j * index + 0.003 * index**2 for index in range(129)],
        dtype=np.complex128,
    )
    _fill_vector(active_rhs, values)
    _fill_vector(condensed_rhs, values)
    authorization_calls: list[int] = []
    caught: tuple[str, str] | None = None
    try:
        def authorize(_payload: Mapping[str, Any]) -> Mapping[str, Any]:
            authorization_calls.append(1)
            if failure_mode == "callback_exception" and comm.rank == 0:
                raise RuntimeError("synthetic conditional callback failure")
            return {"authorized": comm.rank == 0}

        try:
            run_exact_interface_fgmres(
                interface_operator=matrix,
                schur_action=_CopyRecovery(),
                bare_operator=matrix,
                condensed_rhs=condensed_rhs,
                active_rhs=active_rhs,
                interior_rhs_by_group={},
                right_preconditioner=None,
                label=f"conditional_{failure_mode}",
                restart=32,
                mandatory_checkpoints=(16, 32, 64, 128),
                conditional_checkpoints=(256,),
                authorize_conditional=authorize,
                resource_callback=lambda: {"rss_bytes": 123},
                max_iterations=256,
            )
        except ExactQualificationContractError as exc:
            caught = (type(exc).__name__, str(exc))
        assert caught is not None
        assert comm.allgather(caught) == [caught, caught]
        assert comm.allgather(len(authorization_calls)) == [1, 1]
        assert comm.allgather("conditional-decision-after-failure") == [
            "conditional-decision-after-failure",
            "conditional-decision-after-failure",
        ]
    finally:
        active_rhs.destroy()
        condensed_rhs.destroy()
        matrix.destroy()
