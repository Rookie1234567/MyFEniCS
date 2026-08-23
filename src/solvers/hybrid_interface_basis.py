"""Narrow Task040 artificial-interface basis and row-mapping helpers.

The helpers in this module keep the finite-element rows distributed.  They
adapt the existing trace lifter and selected-mode stream through callbacks;
they do not import benchmark code, create a QEP, or hydrate a packet basis.
The only arrays retained by the basis builders are owner-local rows by mode.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from petsc4py import PETSc

__all__ = [
    "build_group_basis_columns",
    "build_lower_fourier_trace_columns",
    "build_mass_dual_columns",
    "build_mass_dual_from_active_vec",
    "canonical_basis_metadata_sha256",
    "canonical_external_mode_metadata_sha256",
    "canonical_mode_keys_sha256",
    "canonical_selected_packet_beta_sha256",
    "collect_streamed_trace_basis",
    "build_artificial_gamma_column",
    "map_lifted_trace_to_gamma_rows",
    "tangential_fourier_trace",
]


def _field(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        return record[name]
    return getattr(record, name)


def _complex_pair(value: complex) -> list[float]:
    value = complex(value)
    if not np.isfinite(value):
        raise ValueError("basis metadata contains non-finite complex data")
    return [float(value.real), float(value.imag)]


def _mode_key(mode: Any) -> dict[str, Any]:
    return {
        "m": int(_field(mode, "m")),
        "n": int(_field(mode, "n")),
        "polarization": str(_field(mode, "polarization")),
        "side": str(_field(mode, "side")),
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, complex):
        return _complex_pair(value)
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"basis metadata value is not JSON-safe: {type(value)!r}")


def _canonical_key(value: Any) -> Any:
    return _json_safe(value)


def _hash_json(value: Any) -> str:
    payload = json.dumps(
        _json_safe(value), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_basis_metadata_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    """Hash ordered, JSON-safe mode metadata without sorting the columns."""

    return _hash_json(list(records))


def canonical_mode_keys_sha256(keys: Sequence[Any]) -> str:
    """Hash the ordered canonical mode-key list."""

    return _hash_json(list(keys))


def canonical_selected_packet_beta_sha256(betas: Sequence[complex]) -> str:
    """Hash beta pairs with the selected-mode packet's existing schema."""

    return _hash_json(list(betas))


def canonical_external_mode_metadata_sha256(
    records: Sequence[Mapping[str, Any]],
) -> str:
    """Hash resolved external inventory mode records with its own schema.

    The record shape is the one emitted by
    ``src.io.input_validation._task039_inventory_from_modes``: side, m, n,
    polarization, beta, propagating, and rayleigh_warning.  It is distinct
    from the selected-packet beta-pair hash.
    """

    return _hash_json(list(records))


def tangential_fourier_trace(
    e_vector: Sequence[complex],
    alpha: complex,
    gamma: complex,
    kz: complex,
    xy: np.ndarray,
    interface_z: float,
) -> np.ndarray:
    """Evaluate one tangential Fourier trace at owner-local points."""

    points = np.asarray(xy, dtype=np.float64)
    vector = np.asarray(e_vector, dtype=np.complex128)
    if points.ndim != 2 or points.shape[1] != 2:
        raise ValueError("Fourier trace coordinates must have shape (rows, 2)")
    if vector.ndim != 1 or vector.size < 2:
        raise ValueError("Fourier trace needs at least two electric components")
    phase = np.exp(
        1j
        * (
            complex(alpha) * points[:, 0]
            + complex(gamma) * points[:, 1]
            + complex(kz) * float(interface_z)
        )
    )
    values = phase[:, None] * vector[None, :2]
    if not np.isfinite(values).all():
        raise ValueError("Fourier trace contains non-finite values")
    return np.asarray(values, dtype=np.complex128)


def build_lower_fourier_trace_columns(
    modes: Sequence[Any],
    xy: np.ndarray,
    interface_z: float,
    *,
    expected_count: int,
    expected_keys: Sequence[Any],
    expected_key_sha256: str,
    expected_metadata: Sequence[Mapping[str, Any]],
    expected_metadata_sha256: str,
    frozen_manifest_beta_metadata_sha256: str,
    trace_to_gamma: Callable[[np.ndarray, Mapping[str, Any]], np.ndarray],
) -> dict[str, Any]:
    """Build owner-local lower outgoing columns in frozen mode order.

    ``modes`` is the ordered output of ``outgoing_port_modes_3d``.  The
    ``expected_count`` argument is 296 for the frozen Task040 lower basis and
    is explicit so tiny tests can use a smaller, still identity-checked,
    authority fixture.
    """

    if len(modes) != int(expected_count) or int(expected_count) <= 0:
        raise ValueError("lower Fourier mode count differs from frozen authority")
    authority_keys = tuple(_canonical_key(key) for key in expected_keys)
    if len(authority_keys) != int(expected_count):
        raise ValueError("lower Fourier authority key count differs from mode count")
    if canonical_mode_keys_sha256(authority_keys) != str(expected_key_sha256):
        raise ValueError("lower Fourier expected key authority hash is inconsistent")
    frozen_manifest_hash = str(frozen_manifest_beta_metadata_sha256)
    if len(frozen_manifest_hash) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in frozen_manifest_hash
    ):
        raise ValueError("lower Fourier frozen metadata identity is not a SHA256")

    def key_token(key: Mapping[str, Any]) -> str:
        return json.dumps(key, sort_keys=True, separators=(",", ":"))

    mode_by_key: dict[str, Any] = {}
    for mode in modes:
        key = _mode_key(mode)
        token = key_token(key)
        if token in mode_by_key:
            raise ValueError("lower Fourier mode key is duplicated")
        mode_by_key[token] = mode
    authority_tokens = tuple(key_token(key) for key in authority_keys)
    if len(set(authority_tokens)) != len(authority_tokens):
        raise ValueError("lower Fourier authority keys are duplicated")
    if set(mode_by_key) != set(authority_tokens):
        raise ValueError("lower Fourier mode keys have missing or extra entries")

    columns: list[np.ndarray] = []
    metadata: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    external_metadata: list[dict[str, Any]] = []
    for authority_key in authority_keys:
        mode = mode_by_key[key_token(authority_key)]
        key = _mode_key(mode)
        if str(_field(mode, "side")) != "bottom":
            raise ValueError("lower Fourier basis contains a non-bottom mode")
        if int(_field(mode, "vertical_sign")) != -1:
            raise ValueError("lower Fourier mode has the wrong outgoing branch")
        beta = complex(_field(mode, "beta"))
        k_vector = np.asarray(_field(mode, "k_vector"), dtype=np.complex128)
        if k_vector.shape != (3,):
            raise ValueError("lower Fourier mode k-vector must have three entries")
        vector_trace = tangential_fourier_trace(
            _field(mode, "e_vector"),
            _field(mode, "alpha"),
            _field(mode, "gamma"),
            k_vector[2],
            xy,
            interface_z,
        )
        external_metadata_item = {
            "side": str(_field(mode, "side")),
            "m": int(_field(mode, "m")),
            "n": int(_field(mode, "n")),
            "polarization": str(_field(mode, "polarization")),
            "beta": _complex_pair(beta),
            "propagating": bool(_field(mode, "propagating")),
            "rayleigh_warning": bool(_field(mode, "rayleigh_warning")),
        }
        metadata_item = {
            **external_metadata_item,
            "branch": "outgoing_bottom",
            "vertical_sign": -1,
        }
        column = np.asarray(
            trace_to_gamma(vector_trace, metadata_item), dtype=np.complex128
        )
        if column.ndim != 1 or not np.isfinite(column).all():
            raise ValueError(
                "lower Fourier gamma column must be finite and one-dimensional"
            )
        if columns and column.shape != columns[0].shape:
            raise ValueError("lower Fourier gamma ownership changed between modes")
        columns.append(column)
        keys.append(key)
        metadata.append(metadata_item)
        external_metadata.append(external_metadata_item)
    actual_keys = tuple(_canonical_key(key) for key in keys)
    if actual_keys != authority_keys:
        raise ValueError("lower Fourier mode order/key identity differs from authority")
    if canonical_mode_keys_sha256(actual_keys) != str(expected_key_sha256):
        raise ValueError("lower Fourier mode-key hash differs from authority")
    expected_external_metadata = tuple(_json_safe(item) for item in expected_metadata)
    if tuple(external_metadata) != expected_external_metadata:
        raise ValueError("lower Fourier beta/branch metadata differs from authority")
    if canonical_external_mode_metadata_sha256(external_metadata) != str(
        expected_metadata_sha256
    ):
        raise ValueError("lower Fourier metadata hash differs from authority")
    values = np.column_stack(columns)
    return {
        "values": values,
        "keys": actual_keys,
        "metadata": tuple(metadata),
        "mode_count": int(expected_count),
        "basis_global_replicated": False,
        "branch_rule": "outgoing_port_modes_3d:side=bottom,vertical_sign=-1",
        "metadata_sha256": canonical_basis_metadata_sha256(metadata),
        "mode_key_sha256": canonical_mode_keys_sha256(actual_keys),
        "external_mode_metadata_sha256": canonical_external_mode_metadata_sha256(
            external_metadata
        ),
        "resolved_mode_metadata_sha256": canonical_external_mode_metadata_sha256(
            external_metadata
        ),
        "frozen_manifest_beta_metadata_sha256": frozen_manifest_hash,
        "frozen_manifest_beta_metadata_reproducible": False,
    }


def _trace_array(values: Any, *, label: str) -> np.ndarray:
    array = np.asarray(values, dtype=np.complex128)
    if array.ndim != 1 or not np.isfinite(array).all():
        raise ValueError(f"{label} trace must be a finite owner-local scalar vector")
    return array


def collect_streamed_trace_basis(
    stream_columns: Callable[[Callable[..., None]], Mapping[str, Any] | None],
    *,
    indices: Sequence[int],
    trace_from_values: Callable[[np.ndarray, Mapping[str, Any], str], np.ndarray],
    expected_mode_keys: Sequence[Any],
    expected_mode_key_sha256: str,
    expected_betas: Sequence[complex],
    expected_selected_packet_beta_sha256: str,
    expected_branch: str = "positive/forward",
) -> dict[str, Any]:
    """Collect transient packet traces while retaining only local columns.

    The supplied stream is the existing mmap callback adapter.  Each callback
    pair is converted to a transverse owner-local array before the next pair
    is delivered, so no PETSc Vec or full mixed Function is retained here.
    """

    selected = tuple(int(index) for index in indices)
    expected_keys = tuple(_canonical_key(key) for key in expected_mode_keys)
    if len(selected) != len(expected_keys) or not selected:
        raise ValueError("streamed basis indices and expected keys differ")
    if len(expected_betas) != len(expected_keys):
        raise ValueError("streamed beta authority count differs from mode keys")
    if canonical_mode_keys_sha256(expected_keys) != str(expected_mode_key_sha256):
        raise ValueError("streamed expected mode-key authority hash is inconsistent")
    if canonical_selected_packet_beta_sha256(expected_betas) != str(
        expected_selected_packet_beta_sha256
    ):
        raise ValueError("streamed expected selected-packet beta hash is inconsistent")
    right_columns: list[np.ndarray] = []
    left_columns: list[np.ndarray] = []
    metadata: list[dict[str, Any]] = []
    seen: set[int] = set()

    def callback(
        index: int,
        right_local: np.ndarray,
        left_local: np.ndarray,
        info: Mapping[str, Any],
    ) -> None:
        index = int(index)
        position = len(metadata)
        if position >= len(selected) or index != selected[position]:
            raise ValueError("streamed packet column order differs from authority")
        branch = str(info.get("branch"))
        allowed_branches = (
            {"positive", "forward"}
            if expected_branch == "positive/forward"
            else {str(expected_branch)}
        )
        if index in seen or branch not in allowed_branches:
            raise ValueError("streamed packet branch/order identity failed")
        if _canonical_key(info.get("mode_key")) != expected_keys[position]:
            raise ValueError("streamed packet mode key differs from authority")
        if "beta" not in info:
            raise ValueError("streamed packet beta metadata is missing")
        actual_beta = complex(info["beta"])
        if actual_beta != complex(expected_betas[position]):
            raise ValueError("streamed packet beta differs from authority")
        right = _trace_array(
            trace_from_values(np.asarray(right_local), info, "right"), label="right"
        )
        left = _trace_array(
            trace_from_values(np.asarray(left_local), info, "left"), label="left"
        )
        if right.shape != left.shape:
            raise ValueError("streamed right/left trace shapes differ")
        if right_columns and right.shape[0] != right_columns[0].shape[0]:
            raise ValueError("streamed trace ownership rows changed")
        right_columns.append(right)
        left_columns.append(left)
        metadata.append(dict(info))
        seen.add(index)

    stream_result = stream_columns(callback)
    if len(metadata) != len(selected):
        raise ValueError("streamed packet did not deliver every frozen column")
    actual_keys = tuple(_canonical_key(info["mode_key"]) for info in metadata)
    actual_betas = tuple(complex(info["beta"]) for info in metadata)
    if actual_keys != expected_keys:
        raise ValueError("streamed packet mode-key order differs from authority")
    if canonical_mode_keys_sha256(actual_keys) != str(expected_mode_key_sha256):
        raise ValueError("streamed packet mode-key hash differs from authority")
    if canonical_selected_packet_beta_sha256(actual_betas) != str(
        expected_selected_packet_beta_sha256
    ):
        raise ValueError("streamed packet beta hash differs from authority")
    if isinstance(stream_result, Mapping):
        if stream_result.get("arrays_retained") is not False:
            raise ValueError("selected-mode stream retained packet arrays")
        if stream_result.get("consumer_qep_required") is not False:
            raise ValueError("selected-mode stream unexpectedly requires QEP")
    return {
        "right": np.column_stack(right_columns),
        "left": np.column_stack(left_columns),
        "metadata": tuple(_json_safe(info) for info in metadata),
        "mode_keys": expected_keys,
        "metadata_sha256": canonical_basis_metadata_sha256(metadata),
        "mode_key_sha256": canonical_mode_keys_sha256(actual_keys),
        "selected_packet_beta_sha256": canonical_selected_packet_beta_sha256(
            actual_betas
        ),
        "branch_authority": "positive/forward",
        "basis_global_replicated": False,
        "transient_pair_peak": 1,
        "arrays_retained": False,
        "qep_calls": 0,
    }


def build_mass_dual_columns(
    left_local: np.ndarray,
    mass_action: Callable[[np.ndarray], np.ndarray],
) -> np.ndarray:
    """Apply the existing reduced trace mass once per left owner-local column."""

    left = np.asarray(left_local, dtype=np.complex128)
    if left.ndim != 2 or not np.isfinite(left).all():
        raise ValueError("left trace columns must be finite and two-dimensional")
    result: list[np.ndarray] = []
    for column in range(left.shape[1]):
        dual = np.asarray(mass_action(left[:, column].copy()), dtype=np.complex128)
        if dual.shape != (left.shape[0],) or not np.isfinite(dual).all():
            raise ValueError("mass action returned the wrong owner-local shape")
        result.append(dual)
    return np.column_stack(result)


def _owner_local_values(
    values: Mapping[int, complex], originals: np.ndarray
) -> dict[int, complex]:
    expected = {int(value) for value in originals}
    actual = {int(key) for key in values}
    if actual != expected:
        raise ValueError("artificial trace owner values do not match plane rows")
    result = {int(key): complex(value) for key, value in values.items()}
    if not all(np.isfinite(value) for value in result.values()):
        raise ValueError("artificial trace owner values are non-finite")
    return result


def map_lifted_trace_to_gamma_rows(
    source_trace: Any,
    *,
    lift_trace: Callable[[Any], Any],
    constraints: Any,
    plane_original_dofs: Sequence[int],
    gamma_rows_local: Sequence[int],
    homogenize: Callable[[Any], None],
    scatter: Callable[[Any], None],
    read_owned_original_values: Callable[[Any, np.ndarray], Mapping[int, complex]],
    release_lifted: Callable[[Any], None] | None = None,
) -> np.ndarray:
    """Lift a 2D trace and compress its artificial plane to Gamma owner rows.

    ``lift_trace`` is the existing reusable interface lifter.  The read
    callback must return only the plane's independently owned original rows;
    ``original_to_active`` then supplies the condensed row identity.  The
    final array follows the public Schur Gamma order, never the mesh or facet
    order.
    """

    plane = np.asarray(plane_original_dofs, dtype=np.int64)
    gamma = np.asarray(gamma_rows_local, dtype=np.int64)
    if plane.ndim != 1 or gamma.ndim != 1 or len(np.unique(plane)) != len(plane):
        raise ValueError("artificial plane original rows must be unique vectors")
    owned = np.asarray(
        getattr(constraints, "owned_active_original_dofs"), dtype=np.int64
    )
    if not set(int(value) for value in plane).issubset(
        set(int(value) for value in owned)
    ):
        raise ValueError("artificial plane includes a non-owned independent row")
    original_to_active = {
        int(key): int(value)
        for key, value in getattr(constraints, "original_to_active").items()
    }
    expansion_by_original = getattr(constraints, "expansion_by_original", None)
    if expansion_by_original is None:
        raise ValueError("artificial trace constraints lack finalized expansions")
    if any(int(value) not in original_to_active for value in plane):
        raise ValueError("artificial plane row lacks condensed active identity")
    active = np.asarray(
        [original_to_active[int(value)] for value in plane], dtype=np.int64
    )
    if len(np.unique(active)) != len(active) or set(active) != set(gamma):
        raise ValueError("artificial plane active support differs from Gamma rows")
    for original, active_id in zip(plane, active, strict=True):
        if int(original) not in expansion_by_original:
            raise ValueError("artificial plane row lacks finalized support closure")
        expansion_ids, expansion_coefficients = expansion_by_original[int(original)]
        nonzero_ids = [
            int(row)
            for row, coefficient in zip(
                expansion_ids, expansion_coefficients, strict=True
            )
            if coefficient != 0
        ]
        if nonzero_ids != [int(active_id)] or len(expansion_coefficients) != 1:
            raise ValueError("artificial plane row is not an independent active row")

    lifted = None
    try:
        lifted_result = lift_trace(source_trace)
        lifted = lifted_result[0] if isinstance(lifted_result, tuple) else lifted_result
        homogenize(lifted)
        scatter(lifted)
        values = _owner_local_values(read_owned_original_values(lifted, plane), plane)
        by_active = {
            original_to_active[int(original)]: values[int(original)]
            for original in plane
        }
        result = np.asarray([by_active[int(row)] for row in gamma], dtype=np.complex128)
        if not np.isfinite(result).all():
            raise ValueError("compressed artificial trace is non-finite")
        return result
    finally:
        if release_lifted is not None and lifted is not None:
            release_lifted(lifted)


def build_artificial_gamma_column(
    source_trace: Any,
    *,
    system: Any,
    condensed: Any,
    interface_z_nm: float,
    plane_cell_side: str,
    plane_original_dofs: Sequence[int],
    gamma_rows_local: Sequence[int],
    lifter: Any | None = None,
    target_space: Any | None = None,
) -> np.ndarray:
    """Use the existing reusable lifter and MPC to build one Gamma column.

    This is the real runtime adapter used by the later Task040 runner.  The
    caller may pass one reusable lifter for a mode stream; no full packet or
    FE basis is retained by this function.
    """

    from ..coupling.hybrid_internal_modes import _ReusableInterfaceLifter

    active_lifter = lifter
    owns_lifter = active_lifter is None
    if active_lifter is None:
        active_lifter = _ReusableInterfaceLifter(
            system,
            target_space=target_space,
            interface_z_nm=float(interface_z_nm),
            plane_cell_side=str(plane_cell_side),
        )
    constraints = condensed.trace_constraints

    def read_owned(field: Any, originals: np.ndarray) -> Mapping[int, complex]:
        vector = field.x.petsc_vec
        first, last = map(int, vector.getOwnershipRange())
        if len(originals) and (
            int(originals.min()) < first or int(originals.max()) >= last
        ):
            raise ValueError("artificial plane rows are not owned by this rank")
        values = np.asarray(
            vector.getValues(np.asarray(originals, dtype=PETSc.IntType)),
            dtype=np.complex128,
        )
        return {
            int(row): complex(value)
            for row, value in zip(originals, values, strict=True)
        }

    try:
        return map_lifted_trace_to_gamma_rows(
            source_trace,
            lift_trace=active_lifter.lift,
            constraints=constraints,
            plane_original_dofs=plane_original_dofs,
            gamma_rows_local=gamma_rows_local,
            homogenize=system.floquet_data.mpc.homogenize,
            scatter=lambda field: field.x.scatter_forward(),
            read_owned_original_values=read_owned,
        )
    finally:
        if owns_lifter:
            del active_lifter


def build_mass_dual_from_active_vec(
    mass: Any,
    condensed: Any,
    gamma_rows_local: Sequence[int],
    left_values: np.ndarray,
    audit: dict[str, Any] | None = None,
) -> np.ndarray:
    """Apply a real reduced mass through full active-layout PETSc Vecs."""

    matrix = getattr(mass, "matrix", mass)
    left = np.asarray(left_values, dtype=np.complex128)
    gamma = np.asarray(gamma_rows_local, dtype=np.int64)
    if left.ndim != 2 or left.shape[0] != len(gamma):
        raise ValueError("mass dual input must be (gamma_local_rows, mode_count)")
    active = condensed.create_active_vector()
    target = active.duplicate()
    try:
        first, last = map(int, active.getOwnershipRange())
        if len(gamma) and (int(gamma.min()) < first or int(gamma.max()) >= last):
            raise ValueError("Gamma rows do not match active Vec ownership")
        positions = gamma - first
        result = np.empty_like(left)
        for column in range(left.shape[1]):
            active.set(0)
            if len(positions):
                active.array[positions] = left[:, column]
            active.assemble()
            target.set(0)
            matrix.mult(active, target)
            if len(positions):
                result[:, column] = target.array[positions]
        if not np.isfinite(result).all():
            raise ValueError("mass dual action returned non-finite values")
        if audit is not None:
            audit.update(
                {
                    "mass_action_count": int(left.shape[1]),
                    "mass_integrated_once": True,
                    "mass_source": "ArtificialZTraceMass.matrix",
                }
            )
        return result
    finally:
        target.destroy()
        active.destroy()


def build_group_basis_columns(
    group: int,
    group_rows_local: Sequence[int],
    lower_rows_local: Sequence[int],
    lower_values: np.ndarray,
    upper_rows_local: Sequence[int],
    upper_values: np.ndarray,
) -> np.ndarray:
    """Place lower/upper owner-local columns in one frozen Gamma row order."""

    group = int(group)
    if group not in {0, 1, 2}:
        raise ValueError("Task040 has exactly three groups")
    rows = np.asarray(group_rows_local, dtype=np.int64)
    lower_rows = np.asarray(lower_rows_local, dtype=np.int64)
    upper_rows = np.asarray(upper_rows_local, dtype=np.int64)
    lower = np.asarray(lower_values, dtype=np.complex128)
    upper = np.asarray(upper_values, dtype=np.complex128)
    if len(np.unique(rows)) != len(rows) or len(np.unique(lower_rows)) != len(
        lower_rows
    ):
        raise ValueError("group basis rows must be unique")
    if len(np.unique(upper_rows)) != len(upper_rows):
        raise ValueError("upper basis rows must be unique")
    if set(lower_rows) & set(upper_rows):
        raise ValueError("lower and upper artificial supports overlap")
    if lower.ndim != 2 or lower.shape[0] != len(lower_rows):
        raise ValueError("lower basis has the wrong owner-local shape")
    if upper.ndim != 2 or upper.shape[0] != len(upper_rows):
        raise ValueError("upper basis has the wrong owner-local shape")
    expected_rows = {
        0: set(lower_rows),
        1: set(lower_rows) | set(upper_rows),
        2: set(upper_rows),
    }[group]
    if set(rows) != expected_rows:
        raise ValueError("group Gamma rows do not match the two interface supports")
    lower_count = lower.shape[1] if group in {0, 1} else 0
    upper_count = upper.shape[1] if group in {1, 2} else 0
    result = np.zeros((len(rows), lower_count + upper_count), dtype=np.complex128)
    position = {int(row): index for index, row in enumerate(rows)}
    if group in {0, 1}:
        for source, row in enumerate(lower_rows):
            result[position[int(row)], :lower_count] = lower[source]
    if group in {1, 2}:
        for source, row in enumerate(upper_rows):
            result[position[int(row)], lower_count:] = upper[source]
    if not np.isfinite(result).all():
        raise ValueError("group basis contains non-finite values")
    return result
