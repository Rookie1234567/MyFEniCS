from __future__ import annotations

import copy
import hashlib
import json
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np

from src.runners.task41_p0_v4_volume_only_audit import _persist_array
from src.runners.task41_p0_v19_native_rank1 import (
    _TERM_ARRAY_FIELDS,
    _archive_identity_and_refs,
    _array_identity,
    _destroy_split_action_on_exit,
    _json_sha256,
    _native_action_identity,
    _prepare_v19_saved_input_checkpoint,
    _receipt_term_bindings,
    _verify_existing_receipt_matches_fresh,
    _V19_RECEIPT_IDENTITY_FIELDS,
    _validate_fresh_cell_direction,
    _v19_read_state,
    _write_term_archive,
    capture_selected_rank1_cell_terms,
    V19_PROGRESS_SCHEMA,
)
from src.solvers.fullspace_mpc_action import FullspaceMpcFormAction
from src.solvers.fullspace_physical_action import FullspaceSplitVolumeAction


class _FakeFFI:
    NULL = object()

    @staticmethod
    def from_buffer(values: np.ndarray) -> np.ndarray:
        return values

    @staticmethod
    def cast(_ctype: str, values: np.ndarray) -> np.ndarray:
        return values


class _FakeKernel:
    def __init__(self, physical_id: int, calls: list[dict[str, Any]]) -> None:
        self.physical_id = physical_id
        self.calls = calls

    def __call__(
        self, raw: np.ndarray, coefficients: np.ndarray, constants: np.ndarray,
        coordinates: np.ndarray, _entity0: Any, _entity1: Any, _entity2: Any,
    ) -> None:
        self.calls.append({
            "physical_id": self.physical_id,
            "coefficient_row": coefficients.copy(),
            "constants": constants.copy(),
            "coordinates": coordinates.copy(),
        })
        raw[:] = (
            self.physical_id + coefficients[0] + constants[0],
            2 * self.physical_id + coefficients[1] - constants[0],
        )


class _FakeElement:
    space_dimension = 2

    def __init__(self) -> None:
        self.transform_calls: list[tuple[int, tuple[float, ...]]] = []

    def T_apply(self, data: np.ndarray, cell_info: np.ndarray, block_size: int) -> None:
        assert block_size == 1
        info = int(cell_info[0])
        self.transform_calls.append((info, tuple(map(float, data))))
        before = data.copy()
        if info == 0:
            data[:] = (2 * before[0] + before[1], before[0] + 3 * before[1])
        else:
            data[:] = (before[0] - 2 * before[1], 4 * before[0] + before[1])


class _FakeDofMap:
    @staticmethod
    def cell_dofs(cell: int) -> np.ndarray:
        return np.asarray([10 * cell, 10 * cell + 1], dtype=np.int32)

    class _IndexMap:
        @staticmethod
        def local_to_global(values: np.ndarray) -> np.ndarray:
            return np.asarray(values, dtype=np.int64) + 100

    index_map = _IndexMap()


class _FakeCppForm:
    integral_types = {"cell"}

    def __init__(self, domains: tuple[np.ndarray, ...]) -> None:
        self._domains = domains
        self.domain_calls: list[tuple[str, int]] = []
        self.coefficients = [
            SimpleNamespace(
                function_space=SimpleNamespace(
                    element=SimpleNamespace(space_dimension=3)
                )
            )
        ]

    @staticmethod
    def num_integrals(_integral_type: str, kernel_index: int) -> int:
        assert kernel_index == 0
        return 2

    def domains(self, integral_type: str, integral_index: int) -> np.ndarray:
        self.domain_calls.append((integral_type, integral_index))
        return self._domains[integral_index]

    def __getattr__(self, name: str) -> Any:
        if name in {"domain", "coefficient_offsets"}:
            raise AssertionError(f"unsupported guessed API accessed: {name}")
        raise AttributeError(name)


class _FakeCompiledForm:
    rank = 1
    dtype = np.dtype(np.complex128)

    def __init__(
        self,
        cells: tuple[int, int] = (0, 1),
        *,
        module_file: str | None = None,
        code: tuple[str, ...] = ("void fixture_ffcx_kernel(void) {}",),
    ) -> None:
        self.kernel_calls: list[dict[str, Any]] = []
        first, second = cells
        self._cpp_object = _FakeCppForm((
            np.asarray([second, first], dtype=np.int32),
            np.asarray([first, second], dtype=np.int32),
        ))
        kernels = [
            _FakeKernel(3, self.kernel_calls),
            _FakeKernel(11, self.kernel_calls),
        ]
        self.ufcx_form = SimpleNamespace(
            num_coefficients=1,
            # UFCx may compile only a subset of original UFL coefficients.
            original_coefficient_positions=(3,),
            form_integral_offsets=(0, 2, 2, 2, 2, 2),
            form_integral_ids=(3, 11),
            form_integrals=[
                SimpleNamespace(tabulate_tensor_complex128=kernel)
                for kernel in kernels
            ],
        )
        self.module = SimpleNamespace(
            ffi=_FakeFFI(), __name__="fixture_ffcx_module", __file__=module_file
        )
        self.code = code


class _FakeUFLForm:
    def __init__(self, signature: str) -> None:
        self._fixture_signature = signature

    def signature(self) -> str:
        return self._fixture_signature


def _fake_native_action_identity(
    component: str = "curl",
    *,
    selected_cells: tuple[int, ...] = (0, 1),
    compiled: _FakeCompiledForm | None = None,
    module_file: str | None = None,
    bilinear_signature: str = "fixture-bilinear-signature",
    action_signature: str = "fixture-rank1-action-signature",
    jit_options: dict[str, Any] | None = None,
    abi_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if compiled is None:
        compiled = _FakeCompiledForm(
            cells=(int(selected_cells[0]), int(selected_cells[-1])),
            module_file=module_file,
        )
    action = SimpleNamespace(
        _action_form=compiled,
        _local_kernel=None,
        _bilinear_form=_FakeUFLForm(bilinear_signature),
        _action_ufl=_FakeUFLForm(action_signature),
        _jit_options=(
            {"fixture-jit-option": "synthetic-only"}
            if jit_options is None else jit_options
        ),
    )
    return _native_action_identity(
        action,
        component=component,
        integral_type_cell="cell",
        selected_cells=selected_cells,
        abi_identity=(
            {"fixture_abi": "synthetic-not-runtime"}
            if abi_identity is None else abi_identity
        ),
    )


class _FakeMesh:
    def __init__(self, cell_count: int = 2) -> None:
        self.topology = SimpleNamespace(
            create_entity_permutations=lambda: None,
            get_cell_permutation_info=lambda: np.arange(cell_count, dtype=np.uint32) % 2,
        )
        self.geometry = SimpleNamespace(
            dofmap=np.tile(np.asarray([[0, 1], [1, 2]], dtype=np.int32), (cell_count // 2 + 1, 1))[:cell_count],
            x=np.asarray(
                [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
                dtype=np.float64,
            ),
        )


class _FakeFunctionSpace:
    def __init__(self, cell_count: int = 2) -> None:
        self.mesh = _FakeMesh(cell_count)
        self.element = _FakeElement()
        self.dofmap = _FakeDofMap()


def _packed() -> dict[tuple[str, int], np.ndarray]:
    return {
        ("cell", 0): np.asarray(
            [[30 + 1j, 31 + 2j, 32 + 3j], [33 + 4j, 34 + 5j, 35 + 6j]],
            dtype=np.complex128,
        ),
        ("cell", 1): np.asarray(
            [[110 + 7j, 111 + 8j, 112 + 9j], [113 + 10j, 114 + 11j, 115 + 12j]],
            dtype=np.complex128,
        ),
    }


def _sha256(path: Any) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_native_kernel_identity_binds_ufl_code_module_jit_abi_and_integrals(
    tmp_path: Any,
) -> None:
    module_path = tmp_path / "fixture_native_kernel.so"
    module_path.write_bytes(b"synthetic module identity v1")
    compiled = _FakeCompiledForm(module_file=str(module_path))
    baseline = _fake_native_action_identity(compiled=compiled)
    assert baseline["compiled_module"]["module_file_status"] == "HASHED"
    assert baseline["compiled_module"]["module_file_sha256"] == _sha256(module_path)
    assert baseline["ffcx_generated_code_sha256"]
    assert baseline["ufl_signatures"] == {
        "bilinear": "fixture-bilinear-signature",
        "rank1_action": "fixture-rank1-action-signature",
    }
    assert baseline["jit_options"] == {"fixture-jit-option": "synthetic-only"}
    assert baseline["abi_identity"]["fixture_abi"] == "synthetic-not-runtime"
    assert baseline["integral_inventory"]["expected_selected_kernel_invocations"] == 4

    module_path.write_bytes(b"synthetic module identity v2")
    module_changed = _fake_native_action_identity(compiled=compiled)
    assert module_changed["identity_sha256"] != baseline["identity_sha256"]
    assert module_changed["compiled_module"]["module_file_sha256"] != baseline[
        "compiled_module"
    ]["module_file_sha256"]

    code_changed = _fake_native_action_identity(
        compiled=_FakeCompiledForm(
            module_file=str(module_path), code=("void different_kernel(void) {}",)
        )
    )
    assert code_changed["identity_sha256"] != module_changed["identity_sha256"]
    ufl_changed = _fake_native_action_identity(
        compiled=compiled, action_signature="different-action-signature"
    )
    assert ufl_changed["identity_sha256"] != module_changed["identity_sha256"]
    jit_changed = _fake_native_action_identity(
        compiled=compiled, jit_options={"fixture-jit-option": "changed"}
    )
    assert jit_changed["identity_sha256"] != module_changed["identity_sha256"]
    abi_changed = _fake_native_action_identity(
        compiled=compiled, abi_identity={"fixture_abi": "different-stack"}
    )
    assert abi_changed["identity_sha256"] != module_changed["identity_sha256"]


def test_native_integral_inventory_change_fails_before_pack_or_kernel() -> None:
    compiled = _FakeCompiledForm()
    identity = _fake_native_action_identity(compiled=compiled)
    compiled._cpp_object._domains = (
        np.asarray([77, 0], dtype=np.int32),
        np.asarray([0, 1], dtype=np.int32),
    )
    pack_calls: list[bool] = []
    with np.testing.assert_raises_regex(ValueError, "integral/domain inventory"):
        capture_selected_rank1_cell_terms(
            compiled,
            _FakeFunctionSpace(),
            selected_cells=(0, 1),
            component="curl",
            column=0,
            integral_type_cell="cell",
            native_action_identities={"curl": identity},
            constants=np.asarray([2 + 3j], dtype=np.complex128),
            pack_coefficients=lambda _form: pack_calls.append(True),
            on_term=lambda _term: {},
        )
    assert not pack_calls
    assert not compiled.kernel_calls


def test_saved_vector_loader_layout_closes_npy_header_and_pre_mesh_checkpoint(
    tmp_path: Any,
) -> None:
    active_rows = np.asarray([10, 11, 12], dtype=np.int64)
    bindings: dict[str, dict[str, Any]] = {}
    columns: list[dict[str, Any]] = []
    for column in (0, 1):
        source_path = tmp_path / f"known_field_col{column}.npy"
        np.save(
            source_path,
            np.arange(4, dtype=np.complex128) + column * 1j,
            allow_pickle=False,
        )
        known_field = np.load(source_path, mmap_mode="r", allow_pickle=False)
        assert isinstance(known_field, np.memmap)
        bindings[str(column)] = {
            "shape": list(known_field.shape),
            "dtype": known_field.dtype.str,
            "bytes": source_path.stat().st_size,
            "payload_bytes": known_field.nbytes,
            "npy_data_offset": known_field.offset,
        }
        assert source_path.stat().st_size == known_field.nbytes + known_field.offset
        columns.append({
            "column": column,
            "active_original_rows": active_rows.copy(),
            "known_field": known_field,
        })

    base_identity = {
        "run_id": "fixture-v19",
        "fixed_window_sha256": "a" * 64,
        "known_field_bindings": bindings,
    }
    current_binding = {
        "contract_sha256": "b" * 64,
        "consumer_source_sha": "c" * 40,
        "fixed_window_sha256": "a" * 64,
    }
    progress_path = tmp_path / "task41_p0_v19_native_rank1_progress.json"
    result, state = _prepare_v19_saved_input_checkpoint(
        donor={"columns": columns},
        known_bindings=bindings,
        trace_rows=3,
        storage_rows=4,
        selected_row=1,
        selected_original_row=11,
        base_run_identity=base_identity,
        current_binding=current_binding,
        progress_path=progress_path,
    )
    assert np.array_equal(result, active_rows)
    saved_state = json.loads(progress_path.read_text(encoding="utf-8"))
    assert saved_state == state
    assert saved_state["run_identity"] == base_identity
    assert saved_state["consumer_execution_bindings"] == [current_binding]

    bad_map_path = tmp_path / "bad_map" / "progress.json"
    broken_columns = [dict(record) for record in columns]
    broken_columns[1]["active_original_rows"] = np.asarray([10, 99, 12], dtype=np.int64)
    with np.testing.assert_raises_regex(ValueError, "active/original row map differs"):
        _prepare_v19_saved_input_checkpoint(
            donor={"columns": broken_columns},
            known_bindings=bindings,
            trace_rows=3,
            storage_rows=4,
            selected_row=1,
            selected_original_row=11,
            base_run_identity=base_identity,
            current_binding=current_binding,
            progress_path=bad_map_path,
        )
    assert not bad_map_path.exists()

    for key, bad_value in (
        ("bytes", bindings["0"]["bytes"] + 1),
        ("shape", [5]),
        ("dtype", np.dtype(np.complex64).str),
    ):
        bad_bindings = copy.deepcopy(bindings)
        bad_bindings["0"][key] = bad_value
        bad_path = tmp_path / f"bad_{key}.json"
        with np.testing.assert_raises_regex(ValueError, "known field column 0 layout differs"):
            _prepare_v19_saved_input_checkpoint(
                donor={"columns": columns},
                known_bindings=bad_bindings,
                trace_rows=3,
                storage_rows=4,
                selected_row=1,
                selected_original_row=11,
                base_run_identity=base_identity,
                current_binding=current_binding,
                progress_path=bad_path,
            )
        assert not bad_path.exists()


def test_saved_progress_with_terms_requires_frozen_native_identity(tmp_path: Any) -> None:
    path = tmp_path / "progress.json"
    base_identity = {"source_sha256": "a" * 64, "cells": [7873, 8014]}
    payload = {
        "schema": V19_PROGRESS_SCHEMA,
        "run_identity": base_identity,
        "run_identity_sha256": _json_sha256(base_identity),
        "consumer_execution_bindings": [],
        "terms": {"saved-term": {"archive_sha256": "b" * 64}},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with np.testing.assert_raises_regex(ValueError, "another numerical input/window"):
        _v19_read_state(path, base_identity)


def test_split_action_cleanup_runs_when_post_creation_preflight_fails() -> None:
    class _Action:
        def __init__(self) -> None:
            self.destroy_calls = 0

        def destroy(self) -> None:
            self.destroy_calls += 1

    action = _Action()
    with np.testing.assert_raises_regex(RuntimeError, "preflight"):
        with _destroy_split_action_on_exit(action):
            raise RuntimeError("synthetic preflight")
    assert action.destroy_calls == 1


def test_split_capture_reaches_native_callback_in_order_and_persists_each_term(
    tmp_path: Any,
) -> None:
    space = _FakeFunctionSpace()
    persisted_order: list[tuple[int, int, int]] = []
    persisted_arrays: dict[tuple[str, int, int, int, str], np.ndarray] = {}
    callback_calls: list[tuple[str, int]] = []

    def save_each_term(term: Any) -> dict[str, Any]:
        persisted_order.append((
            int(term["cpp_integral_index"]),
            int(term["ufcx_physical_integral_id"]),
            int(term["cell_index"]),
        ))
        component = str(term["component"])
        prefix = (
            f"{component}_col{term['column']}_cell{term['cell_index']}_"
            f"integral{term['cpp_integral_index']}"
        )
        artifacts = {}
        for name in (
            "raw_kernel_output", "oriented_test_vector", "packed_coefficient_row",
            "packed_constants", "local_dofs", "original_dofs", "geometry_dof_indices",
            "geometry_coordinates",
        ):
            record = _persist_array(
                tmp_path,
                f"{prefix}_{name}",
                np.asarray(term[name]),
                sha256_file=_sha256,
            )
            artifacts[name] = record
            loaded = np.load(record["path"], allow_pickle=False)
            assert loaded.shape == np.asarray(term[name]).shape
            assert loaded.dtype == np.asarray(term[name]).dtype
            assert _sha256(__import__("pathlib").Path(record["path"])) == record["sha256"]
            persisted_arrays[(
                component,
                int(term["column"]),
                int(term["cell_index"]),
                int(term["cpp_integral_index"]),
                name,
            )] = loaded
        return artifacts

    class _CaptureAction:
        _local_kernel = None

        def __init__(self, component: str) -> None:
            self.component = component
            self.compiled = _FakeCompiledForm()

        def capture_selected_rank1_cell_terms(
            self, source: np.ndarray, callback: Any, **kwargs: Any
        ) -> Any:
            assert np.array_equal(source, np.asarray([5 + 2j, -1 + 3j]))
            callback_calls.append((self.component, int(kwargs["column"])))
            return callback(
                self.compiled,
                space,
                constants=np.asarray([2 + 3j], dtype=np.complex128),
                pack_coefficients=lambda _form: _packed(),
                on_term=save_each_term,
                release_term_arrays_after_callback=True,
                **kwargs,
            )

    split = FullspaceSplitVolumeAction.__new__(FullspaceSplitVolumeAction)
    split._curl_action = _CaptureAction("curl")
    split._mass_action = _CaptureAction("material_mass")
    split._destroyed = False
    source = np.asarray([5 + 2j, -1 + 3j], dtype=np.complex128)
    result = split.capture_selected_rank1_cell_terms(
        source,
        capture_selected_rank1_cell_terms,
        selected_cells=(0, 1),
        column=0,
        integral_type_cell="cell",
        native_action_identities={
            component: _fake_native_action_identity(component)
            for component in ("curl", "material_mass")
        },
    )
    assert result["component_order"] == ["curl", "material_mass"]
    assert result["combine_semantics"] == "curl_result.axpy(1, mass_result)"
    assert callback_calls == [("curl", 0), ("material_mass", 0)]
    assert all(
        item["component"] == component
        for component in ("curl", "material_mass")
        for item in result["components"][component]["terms"]
    )
    compiled = split._curl_action.compiled
    space_element = space.element
    assert persisted_arrays[("curl", 0, 0, 0, "raw_kernel_output")].tolist() == [38 + 7j, 38 + 2j]
    assert persisted_arrays[("curl", 0, 0, 0, "oriented_test_vector")].tolist() == [114 + 16j, 152 + 13j]
    assert persisted_arrays[("curl", 0, 1, 0, "raw_kernel_output")].tolist() == [35 + 4j, 35 - 1j]
    assert persisted_arrays[("curl", 0, 1, 0, "oriented_test_vector")].tolist() == [-35 + 6j, 175 + 15j]
    assert result["components"]["curl"]["original_coefficient_positions"] == [3]
    assert compiled.kernel_calls and space_element.transform_calls
    for component in ("curl", "material_mass"):
        timings = result["components"][component]["stage_timings_seconds"]
        assert set(timings) == {
            "coefficient_table_packing_seconds",
            "selected_coefficient_row_packing_seconds",
            "kernel_execution_seconds",
            "direction_transform_seconds",
            "term_archive_save_seconds",
        }
        assert all(isinstance(value, float) and value >= 0.0 for value in timings.values())

    assert all(
        item["array_artifacts"]
        and set(item["array_artifacts"]) == {
            "raw_kernel_output", "oriented_test_vector", "packed_coefficient_row",
            "packed_constants", "local_dofs", "original_dofs", "geometry_dof_indices",
            "geometry_coordinates",
        }
        and "raw_kernel_output" not in item
        for component in ("curl", "material_mass")
        for item in result["components"][component]["terms"]
    )
    assert len(persisted_order) == 8


def test_fresh_native_cell_tag_and_permutation_must_match_v17() -> None:
    saved = {"cell_tag": 1, "cell_permutation": 0}
    fresh = {"cell_tag": 1, "cell_permutation": 0}
    _validate_fresh_cell_direction(fresh_cell=fresh, saved_cell=saved, cell=7873)

    for field, wrong in (("cell_tag", 2), ("cell_permutation", 1)):
        mismatched = dict(fresh, **{field: wrong})
        with np.testing.assert_raises_regex(ValueError, "tag/permutation"):
            _validate_fresh_cell_direction(
                fresh_cell=mismatched, saved_cell=saved, cell=7873
            )


def test_native_capture_reopens_hash_bound_terms_without_reexecuting_kernels() -> None:
    persisted: dict[str, dict[str, Any]] = {}

    def first_capture() -> tuple[Any, dict[str, Any]]:
        compiled = _FakeCompiledForm()

        def save(term: Any) -> dict[str, Any]:
            identity = term["term_identity"]["identity_sha256"]
            persisted[identity] = {
                "capture_status": term["capture_status"],
                "capture_error": term["capture_error"],
                "array_artifacts": {
                    field: {"path": f"{identity}/{field}", "sha256": "fixture"}
                    for field in _TERM_ARRAY_FIELDS
                },
                "arrays": {
                    field: np.array(term[field], copy=True)
                    for field in _TERM_ARRAY_FIELDS
                },
            }
            return persisted[identity]["array_artifacts"]

        result = capture_selected_rank1_cell_terms(
            compiled,
            _FakeFunctionSpace(),
            selected_cells=(0, 1),
            component="curl",
            column=0,
            integral_type_cell="cell",
            native_action_identities={"curl": _fake_native_action_identity(compiled=compiled)},
            constants=np.asarray([2 + 3j], dtype=np.complex128),
            pack_coefficients=lambda _form: _packed(),
            on_term=save,
            release_term_arrays_after_callback=True,
        )
        return compiled, result

    first, first_result = first_capture()
    assert len(first.kernel_calls) == 4
    assert first_result["kernel_calls_this_invocation"] == 4

    second = _FakeCompiledForm()

    def reopen(term: Any) -> dict[str, Any]:
        row = persisted[term["term_identity"]["identity_sha256"]]
        for field in term["term_identity"]["array_identities"]:
            assert np.array_equal(term[field], row["arrays"][field])
        return {key: value for key, value in row.items() if key != "arrays"}

    def forbidden_save(_term: Any) -> Any:
        raise AssertionError("hash-bound resume must not persist or rerun a completed term")

    resumed = capture_selected_rank1_cell_terms(
        second,
        _FakeFunctionSpace(),
        selected_cells=(0, 1),
        component="curl",
        column=0,
        integral_type_cell="cell",
        native_action_identities={"curl": _fake_native_action_identity(compiled=second)},
        constants=np.asarray([2 + 3j], dtype=np.complex128),
        pack_coefficients=lambda _form: _packed(),
        on_term=forbidden_save,
        reuse_term=reopen,
        release_term_arrays_after_callback=True,
    )
    assert second.kernel_calls == []
    assert resumed["kernel_calls_this_invocation"] == 0
    assert resumed["hash_bound_terms_reused"] == 4
    assert all(
        term["source"] == "REOPENED_HASH_BOUND_CAPTURE"
        and term["kernel_executed_this_invocation"] is False
        and "raw_kernel_output" not in term
        for term in resumed["terms"]
    )


def test_term_archive_reopen_checks_checkpoint_and_member_hashes(tmp_path: Any) -> None:
    terms_directory = tmp_path / "native_rank1_terms"
    terms_directory.mkdir()
    persisted: list[dict[str, Any]] = []
    compiled = _FakeCompiledForm(cells=(7873, 8014))

    def save(term: Any) -> dict[str, Any]:
        persisted.append({
            **dict(term),
            **{
                field: np.array(term[field], copy=True)
                for field in _TERM_ARRAY_FIELDS
            },
        })
        return {field: {"path": field} for field in _TERM_ARRAY_FIELDS}

    capture_selected_rank1_cell_terms(
        compiled,
        _FakeFunctionSpace(cell_count=8015),
        selected_cells=(7873, 8014),
        component="curl",
        column=0,
        integral_type_cell="cell",
        native_action_identities={
            "curl": _fake_native_action_identity(
                selected_cells=(7873, 8014), compiled=compiled
            )
        },
        constants=np.asarray([2 + 3j], dtype=np.complex128),
        pack_coefficients=lambda _form: _packed(),
        on_term=save,
    )
    term = persisted[0]
    product = _write_term_archive(
        term, term_directory=terms_directory, output_directory=tmp_path
    )
    archive_path = terms_directory / (
        f"curl_col0_cell{term['cell_index']}_integral{term['cpp_integral_index']:03d}.npz"
    )
    reopened = _archive_identity_and_refs(
        archive_path,
        output_directory=tmp_path,
        expected_identity=term["term_identity"],
        expected_archive_sha256=product["archive_sha256"],
    )
    assert reopened["archive_binding_status"] == "CHECKPOINT_SHA256_VERIFIED"

    with np.load(archive_path, allow_pickle=False) as saved:
        arrays = {name: np.asarray(saved[name]).copy() for name in saved.files}
    metadata = json.loads(str(arrays["term_metadata"].item()))
    arrays["oriented_test_vector"][0] += 1
    # Re-sign the embedded output identity. A self-consistent archive must
    # still fail when it no longer matches the external progress/receipt SHA.
    metadata["capture_array_identities"]["oriented_test_vector"] = _array_identity(
        arrays["oriented_test_vector"]
    )
    arrays["term_metadata"] = np.asarray(json.dumps(metadata, sort_keys=True))
    with archive_path.open("wb") as stream:
        np.savez(stream, **arrays)
    with np.testing.assert_raises_regex(ValueError, "checkpoint"):
        _archive_identity_and_refs(
            archive_path,
            output_directory=tmp_path,
            expected_identity=term["term_identity"],
            expected_archive_sha256=product["archive_sha256"],
        )
    with np.testing.assert_raises_regex(ValueError, "orphan adoption must be explicit"):
        _archive_identity_and_refs(
            archive_path,
            output_directory=tmp_path,
            expected_identity=term["term_identity"],
        )
    orphan = _archive_identity_and_refs(
        archive_path,
        output_directory=tmp_path,
        expected_identity=term["term_identity"],
        allow_orphan_atomic_archive=True,
    )
    assert orphan["archive_binding_status"] == "ORPHAN_ATOMIC_ARCHIVE_INTERNAL_IDENTITY_ONLY"

    # Input/map members have a second, fresh-input binding through term_identity.
    with np.load(archive_path, allow_pickle=False) as saved:
        arrays = {name: np.asarray(saved[name]).copy() for name in saved.files}
    metadata = json.loads(str(arrays["term_metadata"].item()))
    arrays["original_dofs"][0] += 1
    metadata["capture_array_identities"]["original_dofs"] = _array_identity(
        arrays["original_dofs"]
    )
    arrays["term_metadata"] = np.asarray(json.dumps(metadata, sort_keys=True))
    with archive_path.open("wb") as stream:
        np.savez(stream, **arrays)
    with np.testing.assert_raises_regex(ValueError, "fresh native inputs"):
        _archive_identity_and_refs(
            archive_path,
            output_directory=tmp_path,
            expected_identity=term["term_identity"],
            allow_orphan_atomic_archive=True,
        )


def test_nonfinite_kernel_result_is_persisted_before_failure() -> None:
    compiled = _FakeCompiledForm()

    def nonfinite_kernel(raw: np.ndarray, *_args: Any) -> None:
        raw[:] = (np.nan + 1j, 2 + 0j)

    compiled.ufcx_form.form_integrals[0].tabulate_tensor_complex128 = nonfinite_kernel
    saved: list[dict[str, Any]] = []

    def preserve(term: Any) -> dict[str, Any]:
        saved.append({
            "status": term["capture_status"],
            "error": term["capture_error"],
            "raw": np.array(term["raw_kernel_output"], copy=True),
            "oriented": np.array(term["oriented_test_vector"], copy=True),
        })
        return {field: {"path": field} for field in _TERM_ARRAY_FIELDS}

    with np.testing.assert_raises_regex(FloatingPointError, "non-finite"):
        capture_selected_rank1_cell_terms(
            compiled,
            _FakeFunctionSpace(),
            selected_cells=(0,),
            component="curl",
            column=0,
            integral_type_cell="cell",
            native_action_identities={
                "curl": _fake_native_action_identity(
                    selected_cells=(0,), compiled=compiled
                )
            },
            constants=np.asarray([2 + 3j], dtype=np.complex128),
            pack_coefficients=lambda _form: _packed(),
            on_term=preserve,
        )
    assert len(saved) == 1
    assert saved[0]["status"] == "CAPTURE_FAILED_RETAINED"
    assert "non-finite" in saved[0]["error"]
    assert not np.isfinite(saved[0]["raw"]).all()
    assert not np.isfinite(saved[0]["oriented"]).all()


class _FakeVector:
    def __init__(self, values: np.ndarray, events: list[str], name: str) -> None:
        self.values = values.copy()
        self.events = events
        self.name = name

    def axpy(self, alpha: complex, other: "_FakeVector") -> None:
        self.events.append("axpy")
        self.values += alpha * other.values


def _fake_restricting_action(
    raw_values: np.ndarray,
    source_values: np.ndarray,
    *,
    identity: bool,
    events: list[str],
    name: str,
) -> Any:
    action = FullspaceMpcFormAction.__new__(FullspaceMpcFormAction)
    action._destroyed = False
    action._mpc = object()
    action._owned_rows = 2
    action._ghost_rows = 0
    action._flat_slave_indices = np.asarray([1], dtype=np.int32)
    action._master_indices = np.asarray([0], dtype=np.int32)
    action._conjugated_master_coefficients = np.asarray([2 - 3j], dtype=np.complex128)
    action._constraint_work = np.empty(1, dtype=np.complex128)
    action._slave_indices = np.asarray([1], dtype=np.int32)
    action._owned_slave_indices = np.asarray([1], dtype=np.int32)
    action._slave_row_identity = identity
    action._raw_values = raw_values.copy()
    action._source_values = source_values.copy()
    action._events = events
    action._name = name

    def apply(source: Any) -> _FakeVector:
        action._events.append(action._name)
        raw = action._raw_values.copy()
        FullspaceMpcFormAction._apply_mpc_restriction_to_local(action, raw)
        if action._slave_row_identity:
            raw[action._owned_slave_indices] = action._source_values[
                action._owned_slave_indices
            ]
        return _FakeVector(raw, events, name)

    action.apply = apply
    return action


def test_nonhermitian_mpc_is_applied_per_component_before_split_axpy() -> None:
    events: list[str] = []
    source = np.asarray([5 + 2j, 7 + 5j], dtype=np.complex128)
    split = FullspaceSplitVolumeAction.__new__(FullspaceSplitVolumeAction)
    split._curl_action = _fake_restricting_action(
        np.asarray([1 + 2j, 4 - 1j]), source, identity=True,
        events=events, name="curl",
    )
    split._mass_action = _fake_restricting_action(
        np.asarray([3 - 4j, -2 + 6j]), source, identity=False,
        events=events, name="material_mass",
    )
    split._destroyed = False
    split._apply_count = 0

    result = split.apply(source)
    assert events == ["curl", "material_mass", "axpy"]
    assert result.values.tolist() == [23 + 2j, 7 + 5j]
    assert split._apply_count == 1

    incorrectly_double_owned_identity = _fake_restricting_action(
        np.asarray([3 - 4j, -2 + 6j]), source, identity=True,
        events=[], name="wrong_mass_identity",
    ).apply(source).values
    assert incorrectly_double_owned_identity[1] == source[1]
    assert result.values[1] != source[1] + incorrectly_double_owned_identity[1]


def test_fullspace_local_kernel_apply_and_component_keep_coefficient_source() -> None:
    class _LocalForm:
        def __init__(self, values: np.ndarray) -> None:
            self.array_w = values

        def __enter__(self) -> "_LocalForm":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def set(self, value: complex) -> None:
            self.array_w.fill(value)

    class _OutputVector:
        def __init__(self) -> None:
            self.local = _LocalForm(np.zeros(2, dtype=np.complex128))
            self.ghost_updates: list[dict[str, Any]] = []

        def localForm(self) -> _LocalForm:
            return self.local

        def ghostUpdate(self, **kwargs: Any) -> None:
            self.ghost_updates.append(kwargs)

    class _LocalKernel:
        audit = {"temporary_budget_bytes": 0}

        def __init__(self) -> None:
            self.calls: list[tuple[str, np.ndarray]] = []

        def apply(self, coefficient: np.ndarray, output: np.ndarray) -> None:
            self.calls.append(("apply", coefficient.copy()))
            output[:] = coefficient + np.asarray([1 + 2j, 3 - 1j])

        def apply_component(
            self, coefficient: np.ndarray, output: np.ndarray, *, component: str
        ) -> None:
            self.calls.append((component, coefficient.copy()))
            output[:] = 2 * coefficient

    def make_action() -> tuple[Any, _LocalKernel, _OutputVector]:
        action = FullspaceMpcFormAction.__new__(FullspaceMpcFormAction)
        action._destroyed = False
        action._owned_rows = 2
        action._ghost_rows = 0
        action._mpc = None
        action._slave_row_identity = False
        action._owned_slave_indices = np.empty(0, dtype=np.int32)
        coefficient_x = SimpleNamespace(
            array=np.zeros(2, dtype=np.complex128), scatter_forward=lambda: None
        )
        action._coefficient = SimpleNamespace(x=coefficient_x)
        action._output_vector = _OutputVector()
        action._local_kernel = _LocalKernel()
        action._audit = {
            "apply_count": 0,
            "timing_cumulative": {
                "input_mpc_seconds": 0.0,
                "volume_seconds": 0.0,
                "restriction_rh_seconds": 0.0,
                "ghost_seconds": 0.0,
                "apply_seconds": 0.0,
            },
        }
        return action, action._local_kernel, action._output_vector

    class _Source:
        def __init__(self, values: np.ndarray) -> None:
            self.values = values

        def getArray(self, *, readonly: bool) -> np.ndarray:
            assert readonly is True
            return self.values

    source_values = np.asarray([2 + 5j, -4 + 3j], dtype=np.complex128)
    source = _Source(source_values)

    action, kernel, output = make_action()
    result = action.apply(source)
    assert result is output
    assert len(kernel.calls) == 1
    assert kernel.calls[0][0] == "apply"
    np.testing.assert_array_equal(kernel.calls[0][1], source_values)
    assert output.local.array_w.tolist() == [3 + 7j, -1 + 2j]

    component_action, component_kernel, component_output = make_action()
    component_result = component_action.apply(source, local_component="curl")
    assert component_result is component_output
    assert len(component_kernel.calls) == 1
    assert component_kernel.calls[0][0] == "curl"
    np.testing.assert_array_equal(component_kernel.calls[0][1], source_values)
    assert component_output.local.array_w.tolist() == [4 + 10j, -8 + 6j]


def test_completed_receipt_reuse_requires_fresh_term_and_archive_bindings() -> None:
    artifacts = {
        name: {
            "path": "native_rank1_terms/curl_col0_cell7873_integral000.npz",
            "member": name,
            "sha256": "a" * 64,
            "bytes": 4096,
            "dtype": "<c16",
            "shape": [2],
        }
        for name in _TERM_ARRAY_FIELDS
    }
    identity = {
        "component": "curl",
        "column": 0,
        "cell_index": 7873,
        "cpp_integral_index": 0,
        "identity_sha256": "b" * 64,
    }
    captures = [
        {
            "component": component,
            "column": column,
            "expected_selected_kernel_invocations": 1,
            "packed_coefficient_bytes_preflight": 128,
            "packed_coefficient_bytes_observed": 128,
            "compiled_coefficient_space_dimensions": [3],
            "original_coefficient_positions": [3],
            "kernel_calls_this_invocation": 1,
            "hash_bound_terms_reused": 0,
            "terms": (
                [
                    {
                        "component": component,
                        "column": column,
                        "cell_index": 7873,
                        "cpp_integral_index": 0,
                        "term_identity": identity,
                        "array_artifacts": artifacts,
                    "archive_sha256": "a" * 64,
                    "archive_binding_status": "CHECKPOINT_SHA256_VERIFIED",
                    "capture_status": "CAPTURED_FINITE",
                    }
                ]
                if component == "curl" and column == 0
                else []
            ),
        }
        for component in ("curl", "material_mass")
        for column in (0, 1)
    ]
    fresh = {field: f"bound:{field}" for field in _V19_RECEIPT_IDENTITY_FIELDS}
    fresh["component_column_captures"] = captures
    original = copy.deepcopy(fresh)

    _verify_existing_receipt_matches_fresh(original, fresh)

    original["component_column_captures"][0]["terms"][0]["array_artifacts"][
        "raw_kernel_output"
    ]["sha256"] = "c" * 64
    with np.testing.assert_raises_regex(ValueError, "archive SHA differs"):
        _verify_existing_receipt_matches_fresh(original, fresh)

    bad_direct_archive_sha = copy.deepcopy(fresh)
    bad_direct_archive_sha["component_column_captures"][0]["terms"][0][
        "archive_sha256"
    ] = "c" * 64
    with np.testing.assert_raises_regex(ValueError, "archive SHA differs"):
        _receipt_term_bindings(bad_direct_archive_sha)


def test_cell_integral_type_uses_public_dolfinx_fem_namespace(monkeypatch: Any) -> None:
    from src.runners.task41_p0_v19_native_rank1 import _dolfinx_cell_integral_type

    expected_cell_type = object()
    public_fem = ModuleType("dolfinx.fem")
    public_fem.IntegralType = SimpleNamespace(cell=expected_cell_type)
    cpp_fem = ModuleType("dolfinx.cpp.fem")
    cpp_fem._IntegralType = SimpleNamespace(cell=object())
    cpp = ModuleType("dolfinx.cpp")
    cpp.fem = cpp_fem
    dolfinx = ModuleType("dolfinx")
    dolfinx.fem = public_fem
    dolfinx.cpp = cpp

    monkeypatch.setitem(sys.modules, "dolfinx", dolfinx)
    monkeypatch.setitem(sys.modules, "dolfinx.fem", public_fem)
    monkeypatch.setitem(sys.modules, "dolfinx.cpp", cpp)
    monkeypatch.setitem(sys.modules, "dolfinx.cpp.fem", cpp_fem)

    assert _dolfinx_cell_integral_type() is expected_cell_type


def test_worker_from_import_closure_resolves_without_calling_worker() -> None:
    import ast
    import importlib
    from pathlib import Path

    worker_path = (
        Path(__file__).resolve().parents[1]
        / "runners"
        / "task41_p0_v19_native_rank1.py"
    )
    tree = ast.parse(worker_path.read_text(encoding="utf-8"))
    worker = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "run_v19_native_rank1_worker"
    )
    imported: set[tuple[str, str]] = set()
    for node in ast.walk(worker):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        module = importlib.import_module(node.module)
        for alias in node.names:
            if alias.name == "*":
                continue
            try:
                getattr(module, alias.name)
            except AttributeError:
                importlib.import_module(f"{node.module}.{alias.name}")
            imported.add((node.module, alias.name))

    assert (
        "src.runners.task41_p0_checker",
        "TASK41_P0_B0_V3_VECTOR_INDEX_SHA256",
    ) in imported
    assert (
        "src.solvers.hcurl_assembly_time_condensation",
        "build_selected_volume_trace_star_metadata",
    ) in imported

    from src.runners.task41_p0_checker import TASK41_P0_B0_V3_VECTOR_INDEX_SHA256

    assert TASK41_P0_B0_V3_VECTOR_INDEX_SHA256 == (
        "332b9e5ed553916808cceccd92542b5086cbdbeaaa298d42d95d18916bb7ade3"
    )
