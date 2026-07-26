#!/usr/bin/env python3
"""Generate/check Task035d cell-tensor-bound local-h authorities.

Attempt 1 qualified the dyadic forest, physical hanging/Floquet graph, and
canonical p4/p5/p6 trace restrictions.  This generator advances only the
component authority: it binds those constraints to actual DOLFINx cell
orientation, an FFCx-compiled p6 cell tensor, static condensation, PETSc
preallocation/insertion, right/left RHS reduction, and full active recovery.

The fixtures are deliberately small.  They do not solve the grating PDE and
therefore confer no accuracy or distributed-scalability credit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping

import basix
from basix.ufl import element
import dolfinx
from dolfinx import default_real_type, fem
import mpi4py
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import petsc4py
from scipy import sparse
from scipy.sparse import linalg as sparse_linalg
import ufl

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.adaptivity.dyadic_hexa_broken_mesh import (  # noqa: E402
    build_broken_dyadic_hexa_carrier,
)
from src.adaptivity.dyadic_hexa_refinement import (  # noqa: E402
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
)
from src.adaptivity.hcurl_broken_cell_trace import (  # noqa: E402
    build_broken_hexa_cell_trace_constraint_map,
)
from src.adaptivity.hcurl_broken_trace_graph import (  # noqa: E402
    build_broken_hexa_trace_constraint_authority,
)
from src.adaptivity.variable_p_entity_map import (  # noqa: E402
    build_variable_p_global_entity_map,
)
from src.solvers.hcurl_variable_p_assembly import (  # noqa: E402
    build_variable_p_condensed_trace_system_from_compiled_form,
    condense_variable_p_active_vector_to_trace,
    recover_variable_p_active_full_vector,
)
from src.solvers.hcurl_variable_p_reduction import (  # noqa: E402
    _reduced_trace_auxiliary_norm,
)


CASE_DIR = Path(__file__).resolve().parent
RECORD_DIR = CASE_DIR / "records"
EXPECTED_V3_RECORD_NAMES = {
    1: "local_h_attempt2_mpi1_v3.json",
    2: "local_h_attempt2_mpi2_v3.json",
    8: "local_h_attempt2_mpi8_v3.json",
}
DIAGNOSTIC_OUTPUT_DIR = Path(
    "/tmp/myfenics-task035d-attempt2-diagnostics"
)
NUMERICAL_FILES = (
    ROOT / "src/adaptivity/dyadic_hexa_refinement.py",
    ROOT / "src/adaptivity/dyadic_hexa_broken_mesh.py",
    ROOT / "src/adaptivity/hcurl_hanging_trace.py",
    ROOT / "src/adaptivity/hcurl_broken_trace_graph.py",
    ROOT / "src/adaptivity/hcurl_broken_cell_trace.py",
    ROOT / "src/adaptivity/hcurl_trace_constraint_graph.py",
    ROOT / "src/adaptivity/exact_sequence_variable_p.py",
    ROOT / "src/adaptivity/variable_p_entity_map.py",
    ROOT / "src/constraints/high_order_floquet_trace.py",
    ROOT / "src/solvers/hcurl_assembly_time_condensation.py",
    ROOT / "src/solvers/hcurl_variable_p_local.py",
    ROOT / "src/solvers/hcurl_variable_p_assembly.py",
    ROOT / "src/solvers/hcurl_variable_p_reduction.py",
    Path(__file__).resolve(),
    (
        Path(__file__).resolve().parent
        / "check_local_h_attempt2_authority.py"
    ),
)
ALLOWED_GENERATED_EVIDENCE = {
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi1_v1.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi2_v1.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi8_v1.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi_identity_v1.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi1_v2.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi2_v2.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi8_v2.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi_identity_v2.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi1_v3.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi2_v3.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi8_v3.json",
    "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
    "records/local_h_attempt2_mpi_identity_v3.json",
}
FIXTURE_CONFIG = {
    "root_cells": [3, 3, 1],
    "refined_root": [0, 0, 0, 0, 0],
    "periodic_axes": ["x", "y"],
    "trace_degree": 5,
    "cell_interior_degree": 6,
    "phase_x": [float(np.cos(0.2)), float(np.sin(0.2))],
    "phase_y": [float(np.cos(-0.3)), float(np.sin(-0.3))],
    "form": "curlcurl + (2.5+0.17j) mass",
}
PRIOR_AUTHORITIES = {
    "phase_a_compact": {
        "path": (
            "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
            "records/compact_authority_v1.json"
        ),
        "sha256": (
            "2e896ef45bbfc5c11901503269d11c0321106c9e41f71729ac7c6fc722687403"
        ),
    },
    "phase_a_reference_active_space": {
        "path": (
            "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
            "records/reference_active_space_authority_v1.json"
        ),
        "sha256": (
            "4c1c5e68540dca4ddcc4165b0cc175abb4671ad254a44c1aa3518e4c9398ea9b"
        ),
    },
    "local_h_attempt1_mpi_identity": {
        "path": (
            "benchmarks/cases/097_goal_oriented_exact_sequence_hp_adaptivity/"
            "records/local_h_attempt1_mpi_identity_v1.json"
        ),
        "sha256": (
            "d341ad69dd52df6bbedcec8a522084cd75ae99fd9fd7d751bab7bfb73655fe44"
        ),
    },
}
ATTEMPT2_HISTORY = {
    "mpi1_v1": (
        "records/local_h_attempt2_mpi1_v1.json",
        "ebe88241242603971eaaba89735c893a5445f416486e02c0fa1b0647a44ddfbc",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "mpi2_v1": (
        "records/local_h_attempt2_mpi2_v1.json",
        "05c526a728538065bb00b49e0d578365173babad18933fd607e4b46d0546e354",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "mpi8_v1": (
        "records/local_h_attempt2_mpi8_v1.json",
        "c0bf2e9b14fd5852d3d65f71aa2fea7c6362ffa96d997eb020bb312ec11df5cd",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "identity_v1_controlled_failure": (
        "records/local_h_attempt2_mpi_identity_v1.json",
        "9afcacd1e855ed08dd2609ae54b5c1de1fb3d97a783bc29d12b76bb767398411",
        "local_h_attempt2_evidence_fail",
        False,
    ),
    "mpi1_v2": (
        "records/local_h_attempt2_mpi1_v2.json",
        "6a4ae7312402e94653206b68ed54a825703f89bef7bbb787d2abf777d3d5a6af",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "mpi2_v2": (
        "records/local_h_attempt2_mpi2_v2.json",
        "b135f618880883d0b9360be3483c0cf0aa786710588a61479db5e845981f2405",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "mpi8_v2": (
        "records/local_h_attempt2_mpi8_v2.json",
        "7814a3bac9da53557218947afec48f9fd8a544eed9cb3c59cafd94baeff08f12",
        "local_h_attempt2_cell_tensor_component_pass_pde_blocked",
        True,
    ),
    "identity_v2_controlled_failure": (
        "records/local_h_attempt2_mpi_identity_v2.json",
        "d72d3bb204c6ed0f2bb57fa701ce81b55f61ee090c2d9247c59679f1df5bed9a",
        "local_h_attempt2_evidence_fail",
        False,
    ),
    "identity_v2_checker_fix1": (
        "records/local_h_attempt2_mpi_identity_v2_checker_fix1.json",
        "63a5aea0c8f10984e7959ce9f186cc36bb5a4a06d207f8f184bcaf2284b10bcd",
        "local_h_attempt2_component_pass_pde_blocked",
        True,
    ),
}
EXPECTED_P5_HANGING_RESTRICTION_SHA256 = (
    "90bd8eb7c612f044c0026ce0551c2f96d8241adc9b63b8e402652b5b738ccf2a"
)


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(
            json.dumps(
                _plain(payload),
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )
    return _sha256(path)


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _plain(payload),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _all_numbers_finite(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_all_numbers_finite(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return all(_all_numbers_finite(item) for item in value)
    if isinstance(value, (float, np.floating)):
        return math.isfinite(float(value))
    return True


def _prior_authority_manifest() -> dict[str, Any]:
    records: dict[str, Any] = {}
    for name, expected in PRIOR_AUTHORITIES.items():
        path = ROOT / expected["path"]
        observed_sha = _sha256(path)
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {value}")
            ),
        )
        if observed_sha != expected["sha256"]:
            raise RuntimeError(
                f"prior Task035d authority hash drifted: {name}"
            )
        if payload.get("pass") is not True:
            raise RuntimeError(
                f"prior Task035d authority has not passed: {name}"
            )
        records[name] = {
            **expected,
            "status": payload.get("status"),
            "pass": True,
        }
        if name == "local_h_attempt1_mpi_identity":
            observed = payload["stable_identity"][
                "canonical_hcurl_restriction_sha256"
            ]["5"]
            if observed != EXPECTED_P5_HANGING_RESTRICTION_SHA256:
                raise RuntimeError(
                    "Attempt1 p5 hanging restriction identity drifted"
                )
            records[name]["p5_hanging_restriction_sha256"] = observed
    return {
        "records": records,
        "phase_a_exact_sequence_hash_bound": True,
        "attempt1_orientation_restriction_hash_bound": True,
        "p5_hanging_restriction_sha256": (
            EXPECTED_P5_HANGING_RESTRICTION_SHA256
        ),
    }


def _attempt2_history_immutability_manifest() -> dict[str, Any]:
    records: dict[str, Any] = {}
    for name, (
        relative,
        expected_sha,
        expected_status,
        expected_pass,
    ) in ATTEMPT2_HISTORY.items():
        path = CASE_DIR / relative
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {value}")
            ),
        )
        if (
            _sha256(path) != expected_sha
            or payload.get("status") != expected_status
            or payload.get("pass") is not expected_pass
        ):
            raise RuntimeError(
                f"Attempt2 historical evidence drifted: {name}"
            )
        records[name] = {
            "path": f"records/{path.name}",
            "sha256": expected_sha,
            "expected_status": expected_status,
            "expected_pass": expected_pass,
        }
    return {
        "records": records,
        "historical_failure_evidence_preserved": True,
        "history_file_count": len(records),
    }


def _live_source_identity(
    comm: MPI.Intracomm,
    *,
    expected_sha: str,
) -> dict[str, Any]:
    if comm.rank == 0:
        try:
            head = subprocess.check_output(
                ("git", "rev-parse", "HEAD"),
                cwd=ROOT,
                text=True,
            ).strip()
            status_lines = tuple(
                line
                for line in subprocess.check_output(
                    (
                        "git",
                        "status",
                        "--short",
                        "--untracked-files=all",
                    ),
                    cwd=ROOT,
                    text=True,
                ).splitlines()
                if line
            )
            disallowed = []
            allowed = []
            for line in status_lines:
                path = line[3:]
                if (
                    line.startswith("?? ")
                    and path in ALLOWED_GENERATED_EVIDENCE
                ):
                    allowed.append(path)
                else:
                    disallowed.append(line)
            packet = {
                "ok": True,
                "error": None,
                "payload": {
                    "head": head,
                    "status_lines": list(status_lines),
                    "allowed_generated_evidence": allowed,
                    "disallowed_status_lines": disallowed,
                },
            }
        except (OSError, subprocess.SubprocessError) as exc:
            packet = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "payload": None,
            }
    else:
        packet = None
    envelope = comm.bcast(packet, root=0)
    if not envelope["ok"]:
        raise RuntimeError(
            f"collective live-source probe failed: {envelope['error']}"
        )
    identity = envelope["payload"]
    if identity["head"] != expected_sha:
        raise RuntimeError(
            "live HEAD differs from the explicitly verified source SHA"
        )
    if identity["disallowed_status_lines"]:
        raise RuntimeError(
            "numerical source is not clean: "
            f"{identity['disallowed_status_lines']}"
        )
    return {
        **identity,
        "verified_clean_numerical_source": True,
        "clean_semantics": (
            "no tracked/staged/unknown changes; previously generated "
            "Attempt2 evidence files are enumerated and allowed"
        ),
    }


def _commit_blob_manifest(source_sha: str) -> dict[str, str]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("solver source SHA is invalid")
    result: dict[str, str] = {}
    for path in NUMERICAL_FILES:
        relative = str(path.relative_to(ROOT))
        content = subprocess.check_output(
            ("git", "show", f"{source_sha}:{relative}"),
            cwd=ROOT,
        )
        result[relative] = hashlib.sha256(content).hexdigest()
    return result


def _collective_environment_preflight(
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    local = {
        "rank": int(comm.rank),
        "qualified_activation": os.environ.get(
            "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
        ),
        "python_executable": sys.executable,
        "dolfinx": dolfinx.__version__,
        "basix": basix.__version__,
        "petsc4py": petsc4py.__version__,
        "mpi4py": mpi4py.__version__,
        "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
        "petsc_int_type": str(np.dtype(PETSc.IntType)),
        "mpi_vendor": _plain(MPI.get_vendor()),
        "mpi_library_version": MPI.Get_library_version().strip(),
    }
    errors = []
    if local["qualified_activation"] != "1":
        errors.append("qualified activation marker is absent")
    if local["petsc_scalar_type"] != "complex128":
        errors.append("PETSc scalar type is not complex128")
    if local["petsc_int_type"] != "int32":
        errors.append("PETSc int type is not int32")
    packets = comm.allgather(
        {
            "environment": local,
            "errors": errors,
        }
    )
    collective_errors = [
        f"rank {packet['environment']['rank']}: {error}"
        for packet in packets
        for error in packet["errors"]
    ]
    comparable = [
        {
            key: value
            for key, value in packet["environment"].items()
            if key != "rank"
        }
        for packet in packets
    ]
    if any(row != comparable[0] for row in comparable[1:]):
        collective_errors.append("MPI ranks use different ABI environments")
    if collective_errors:
        raise RuntimeError(
            "collective Task035d environment preflight failed: "
            + "; ".join(collective_errors)
        )
    return {
        "rank_environments": [
            packet["environment"] for packet in packets
        ],
        "all_ranks_identical": True,
    }


def _degree_array(mesh: Any, dimension: int, degree: int) -> np.ndarray:
    mesh.topology.create_entities(dimension)
    index_map = mesh.topology.index_map(dimension)
    return np.full(
        int(index_map.size_local + index_map.num_ghosts),
        int(degree),
        dtype=np.int32,
    )


def _boxes(
    nx: int,
    ny: int,
    nz: int,
) -> list[tuple[float, float, float, float, float, float]]:
    return [
        (
            float(i),
            float(j),
            float(k),
            float(i + 1),
            float(j + 1),
            float(k + 1),
        )
        for k in range(nz)
        for j in range(ny)
        for i in range(nx)
    ]


def _periodic_corner_fixture(comm: MPI.Intracomm) -> tuple[Any, Any]:
    forest = build_root_dyadic_hexa_forest(
        _boxes(3, 3, 1),
        [1] * 9,
        periodic_axes=("x", "y"),
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    return forest, build_broken_dyadic_hexa_carrier(forest, comm=comm)


def _balanced_counts(total: int, size: int) -> tuple[int, ...]:
    quotient, remainder = divmod(int(total), int(size))
    return tuple(
        quotient + (1 if rank < remainder else 0)
        for rank in range(size)
    )


def _global_vector(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.comm.tompi4py()
    return np.concatenate(
        comm.allgather(
            np.asarray(vector.getArray(readonly=True)).copy()
        )
    )


def _matrix_action(matrix: PETSc.Mat, values: np.ndarray) -> np.ndarray:
    source = matrix.createVecRight()
    target = matrix.createVecLeft()
    start, stop = source.getOwnershipRange()
    source.getArray()[:] = np.asarray(values[start:stop])
    source.assemble()
    matrix.mult(source, target)
    result = _global_vector(target)
    source.destroy()
    target.destroy()
    return result


def _complex_pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _vector_signature(values: np.ndarray) -> dict[str, Any]:
    vector = np.asarray(values, dtype=np.complex128).reshape(-1)
    if not len(vector) or not np.all(np.isfinite(vector)):
        raise ValueError("signature vector must be finite and non-empty")
    scale = max(float(np.max(np.abs(vector))), 1.0e-300)
    normalized = vector / scale
    quantized = np.column_stack(
        (
            np.rint(normalized.real * 1.0e10).astype(np.int64),
            np.rint(normalized.imag * 1.0e10).astype(np.int64),
        )
    )
    indices = np.unique(
        np.linspace(0, len(vector) - 1, 17, dtype=np.int64)
    )
    weights = np.exp(
        1j * 0.031 * np.arange(len(vector), dtype=np.float64)
    )
    return {
        "size": int(len(vector)),
        "linf": scale,
        "l2": float(np.linalg.norm(vector)),
        "sum": _complex_pair(complex(np.sum(vector))),
        "weighted_sum": _complex_pair(
            complex(np.vdot(weights, vector))
        ),
        "normalized_quantized_1e10_sha256": hashlib.sha256(
            np.ascontiguousarray(quantized).view(np.uint8)
        ).hexdigest(),
        "sample_indices": indices.tolist(),
        "normalized_samples": [
            _complex_pair(complex(normalized[index]))
            for index in indices
        ],
    }


def _expected_raw_trace(constraints: Any, root: np.ndarray) -> np.ndarray:
    trace = np.zeros(
        constraints.entity_map.active_trace_rows,
        dtype=np.complex128,
    )
    blocks = getattr(
        constraints,
        "work_owned_entity_blocks",
        tuple(constraints.entity_blocks.values()),
    )
    for block in blocks:
        trace[block.full_rows] = (
            block.full_from_independent @ root[block.independent_rows]
        )
    return np.asarray(
        constraints.entity_map.mesh.comm.allreduce(trace, op=MPI.SUM)
    )


def _global_trace_expansion(constraints: Any) -> sparse.csr_matrix:
    rows: list[int] = []
    columns: list[int] = []
    values: list[complex] = []
    blocks = getattr(
        constraints,
        "work_owned_entity_blocks",
        tuple(constraints.entity_blocks.values()),
    )
    for block in blocks:
        local_rows, local_columns = np.nonzero(
            np.abs(block.full_from_independent) > 0.0
        )
        rows.extend(map(int, block.full_rows[local_rows]))
        columns.extend(
            map(int, block.independent_rows[local_columns])
        )
        values.extend(
            map(
                complex,
                block.full_from_independent[
                    local_rows,
                    local_columns,
                ],
            )
        )
    packets = constraints.entity_map.mesh.comm.allgather(
        (
            np.asarray(rows, dtype=np.int64),
            np.asarray(columns, dtype=np.int64),
            np.asarray(values, dtype=np.complex128),
        )
    )
    return sparse.coo_matrix(
        (
            np.concatenate([packet[2] for packet in packets]),
            (
                np.concatenate([packet[0] for packet in packets]),
                np.concatenate([packet[1] for packet in packets]),
            ),
        ),
        shape=(
            constraints.entity_map.active_trace_rows,
            constraints.independent_trace_rows,
        ),
        dtype=np.complex128,
    ).tocsr()


def _relative_max_error(
    observed: np.ndarray,
    expected: np.ndarray,
) -> tuple[float, float]:
    difference = float(
        np.max(np.abs(np.asarray(observed) - np.asarray(expected)), initial=0.0)
    )
    scale = max(
        float(np.max(np.abs(np.asarray(expected)), initial=0.0)),
        1.0,
    )
    return difference, difference / scale


def _matrix_from_lu_factor(
    factor: tuple[np.ndarray, np.ndarray],
) -> np.ndarray:
    packed, pivots = factor
    size = int(packed.shape[0])
    lower = np.tril(packed, k=-1) + np.eye(
        size,
        dtype=packed.dtype,
    )
    upper = np.triu(packed)
    permuted = lower @ upper
    permutation = np.arange(size)
    for row, pivot in enumerate(pivots):
        permutation[row], permutation[pivot] = (
            permutation[pivot],
            permutation[row],
        )
    matrix = np.empty_like(permuted)
    matrix[permutation] = permuted
    return matrix


def _active_rhs(system: Any, constraints: Any) -> PETSc.Vec:
    comm = system.entity_map.mesh.comm
    values = np.zeros(
        system.entity_map.active_rows,
        dtype=np.complex128,
    )
    root_rows = np.arange(
        constraints.independent_trace_rows,
        dtype=np.float64,
    )
    canonical_trace_root = (
        np.sin(0.029 * root_rows)
        + 1j * np.cos(0.031 * root_rows)
        + 0.02 * np.sin(0.037 * root_rows)
    )
    values[: system.entity_map.active_trace_rows] = (
        _expected_raw_trace(constraints, canonical_trace_root)
    )
    constraint_by_cell = {
        cell.global_cell: cell for cell in constraints.owned_cells
    }
    local_interior_packets = []
    for recovery in system.cell_recovery:
        cell = recovery.cell
        space = recovery.space
        canonical_leaf = constraint_by_cell[cell.global_cell].canonical_leaf
        reference_rhs = np.zeros(
            space.hcurl_dimension,
            dtype=np.complex128,
        )
        mode = (
            canonical_leaf * 1000
            + np.arange(len(space.interior_dofs), dtype=np.float64)
        )
        reference_rhs[space.interior_dofs] = (
            np.sin(0.011 * mode)
            + 1j * np.cos(0.007 * mode)
            + 0.03 * np.cos(0.017 * mode)
        )
        oriented_rhs = space.apply_hcurl_dof_transform(
            reference_rhs,
            cell_info=cell.cell_info,
        )
        local_interior_packets.append(
            (
                np.asarray(cell.interior_rows, dtype=np.int64),
                np.asarray(
                    oriented_rhs[space.interior_dofs],
                    dtype=np.complex128,
                ),
            )
        )
    covered = []
    for packet in comm.allgather(tuple(local_interior_packets)):
        for rows, local_values in packet:
            values[rows] = local_values
            covered.extend(map(int, rows))
    expected_interior = np.arange(
        system.entity_map.active_trace_rows,
        system.entity_map.active_rows,
        dtype=np.int64,
    )
    if not np.array_equal(
        np.sort(np.asarray(covered, dtype=np.int64)),
        expected_interior,
    ):
        raise RuntimeError(
            "canonical active RHS does not cover each interior row once"
        )
    counts = _balanced_counts(system.entity_map.active_rows, comm.size)
    vector = PETSc.Vec().createMPI(
        (counts[comm.rank], system.entity_map.active_rows),
        comm=comm,
    )
    start, stop = vector.getOwnershipRange()
    vector.getArray()[:] = values[start:stop]
    vector.assemble()
    return vector


def _canonical_recovered_values(
    system: Any,
    constraints: Any,
    recovered_values: np.ndarray,
) -> np.ndarray:
    constraint_by_cell = {
        cell.global_cell: cell for cell in constraints.owned_cells
    }
    local_packet = []
    for recovery in system.cell_recovery:
        cell = recovery.cell
        oriented = np.asarray(recovered_values[cell.active_rows])
        reference = recovery.space.apply_hcurl_dof_transform(
            oriented,
            cell_info=cell.cell_info,
            transpose=True,
        )
        local_packet.append(
            (
                int(constraint_by_cell[cell.global_cell].canonical_leaf),
                np.asarray(reference, dtype=np.complex128),
            )
        )
    gathered = [
        row
        for packet in system.entity_map.mesh.comm.allgather(
            tuple(local_packet)
        )
        for row in packet
    ]
    gathered.sort(key=lambda row: row[0])
    if [leaf for leaf, _values in gathered] != list(
        range(len(gathered))
    ):
        raise RuntimeError(
            "canonical recovery does not cover every forest leaf once"
        )
    return np.concatenate([values for _leaf, values in gathered])


def _compiled_form(carrier: Any) -> tuple[Any, Any]:
    mesh = carrier.mesh
    p6_space = fem.functionspace(
        mesh,
        element(
            "N1curl",
            mesh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    trial = ufl.TrialFunction(p6_space)
    test = ufl.TestFunction(p6_space)
    dx = ufl.Measure(
        "dx",
        domain=mesh,
        subdomain_data=carrier.cell_tags,
    )
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(trial), ufl.curl(test))
            + PETSc.ScalarType(2.5 + 0.17j) * ufl.inner(trial, test)
        )
        * dx(1)
    )
    return p6_space, compiled


def _run_compiled_fixture(
    *,
    forest: Any,
    carrier: Any,
    trace_degree: int,
    phase_x: complex = 1.0 + 0.0j,
    phase_y: complex = 1.0 + 0.0j,
) -> dict[str, Any]:
    mesh = carrier.mesh
    entity_map = build_variable_p_global_entity_map(
        mesh,
        edge_degrees=_degree_array(mesh, 1, trace_degree),
        face_degrees=_degree_array(mesh, 2, trace_degree),
        cell_degrees=_degree_array(mesh, 3, 6),
    )
    authority = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=trace_degree,
        phase_x=phase_x,
        phase_y=phase_y,
    )
    constraints = build_broken_hexa_cell_trace_constraint_map(
        forest,
        carrier,
        entity_map,
        authority,
    )
    p6_space, compiled = _compiled_form(carrier)
    raw_system = build_variable_p_condensed_trace_system_from_compiled_form(
        compiled,
        p6_space,
        carrier.cell_tags,
        entity_map,
    )
    system = build_variable_p_condensed_trace_system_from_compiled_form(
        compiled,
        p6_space,
        carrier.cell_tags,
        entity_map,
        trace_constraints=constraints,
    )
    active_rhs = None
    reduced_right = None
    reduced_left = None
    raw_reduced_right = None
    raw_reduced_left = None
    recovered_zero = None
    recovered_rhs = None
    raw_recovered_zero = None
    raw_recovered_rhs = None
    norm_vector = None
    try:
        expansion = _global_trace_expansion(constraints)
        rows = np.arange(
            constraints.independent_trace_rows,
            dtype=np.float64,
        )
        root = np.sin(0.017 * rows) + 1j * np.cos(0.013 * rows)
        probe = np.cos(0.019 * rows) + 1j * np.sin(0.023 * rows)
        action_root = _matrix_action(system.matrix, root)
        action_probe = _matrix_action(system.matrix, probe)
        raw_root = np.asarray(expansion @ root)
        raw_probe = np.asarray(expansion @ probe)
        expected_action_root = np.asarray(
            expansion.conj().T
            @ _matrix_action(raw_system.matrix, raw_root)
        )
        expected_action_probe = np.asarray(
            expansion.conj().T
            @ _matrix_action(raw_system.matrix, raw_probe)
        )
        action_root_abs, action_root_rel = _relative_max_error(
            action_root,
            expected_action_root,
        )
        action_probe_abs, action_probe_rel = _relative_max_error(
            action_probe,
            expected_action_probe,
        )
        observed_bilinear = complex(np.vdot(root, action_probe))
        expected_bilinear = complex(
            np.vdot(
                raw_root,
                _matrix_action(raw_system.matrix, raw_probe),
            )
        )
        bilinear_abs = abs(observed_bilinear - expected_bilinear)
        bilinear_rel = bilinear_abs / max(
            abs(expected_bilinear),
            1.0,
        )

        active_rhs = _active_rhs(system, constraints)
        reduced_right = condense_variable_p_active_vector_to_trace(
            system,
            active_rhs,
            side="right",
        )
        reduced_left = condense_variable_p_active_vector_to_trace(
            system,
            active_rhs,
            side="left",
        )
        raw_reduced_right = condense_variable_p_active_vector_to_trace(
            raw_system,
            active_rhs,
            side="right",
        )
        raw_reduced_left = condense_variable_p_active_vector_to_trace(
            raw_system,
            active_rhs,
            side="left",
        )
        right_values = _global_vector(reduced_right)
        left_values = _global_vector(reduced_left)
        expected_right = np.asarray(
            expansion.conj().T @ _global_vector(raw_reduced_right)
        )
        expected_left = np.asarray(
            expansion.conj().T @ _global_vector(raw_reduced_left)
        )
        right_abs, right_rel = _relative_max_error(
            right_values,
            expected_right,
        )
        left_abs, left_rel = _relative_max_error(
            left_values,
            expected_left,
        )
        recovered_zero = recover_variable_p_active_full_vector(
            system,
            root,
        )
        recovered_rhs = recover_variable_p_active_full_vector(
            system,
            root,
            active_full_rhs=active_rhs,
        )
        raw_recovered_zero = recover_variable_p_active_full_vector(
            raw_system,
            raw_root,
        )
        raw_recovered_rhs = recover_variable_p_active_full_vector(
            raw_system,
            raw_root,
            active_full_rhs=active_rhs,
        )
        recovered_zero_values = _global_vector(recovered_zero)
        recovered_rhs_values = _global_vector(recovered_rhs)
        canonical_recovered_zero_values = _canonical_recovered_values(
            system,
            constraints,
            recovered_zero_values,
        )
        canonical_recovered_rhs_values = _canonical_recovered_values(
            system,
            constraints,
            recovered_rhs_values,
        )
        raw_recovered_zero_values = _global_vector(raw_recovered_zero)
        raw_recovered_rhs_values = _global_vector(raw_recovered_rhs)
        zero_recovery_abs, zero_recovery_rel = _relative_max_error(
            recovered_zero_values,
            raw_recovered_zero_values,
        )
        rhs_recovery_abs, rhs_recovery_rel = _relative_max_error(
            recovered_rhs_values,
            raw_recovered_rhs_values,
        )
        expected_trace = _expected_raw_trace(constraints, root)
        trace_error = float(
            np.max(
                np.abs(
                    recovered_zero_values[
                        : entity_map.active_trace_rows
                    ]
                    - expected_trace
                ),
                initial=0.0,
            )
        )
        local_recovery_error = 0.0
        recovered_by_cell = {
            cell.global_cell: (cell, local_active)
            for cell, local_active in system.recover_owned_active_cells(
                root,
                active_full_rhs=active_rhs,
            )
        }
        for cell, local_active in recovered_by_cell.values():
            local_recovery_error = max(
                local_recovery_error,
                float(
                    np.max(
                        np.abs(
                            local_active
                            - recovered_rhs_values[cell.active_rows]
                        ),
                        initial=0.0,
                    )
                ),
            )
        local_recovery_error = float(
            mesh.comm.allreduce(local_recovery_error, op=MPI.MAX)
        )
        active_rhs_values = _global_vector(active_rhs)
        zero_equation_residual = 0.0
        nonzero_equation_residual = 0.0
        for recovery in system.cell_recovery:
            cell = recovery.cell
            space = recovery.space
            factor = system.interior_lu_by_class[recovery.class_key]
            A_ii = _matrix_from_lu_factor(factor)
            interior_from_trace = system.interior_from_trace_by_class[
                recovery.class_key
            ]
            A_it = -A_ii @ interior_from_trace
            trace_positions = np.asarray(space.trace_dofs, dtype=np.int64)
            interior_positions = np.asarray(
                space.interior_dofs,
                dtype=np.int64,
            )
            zero_local = recovered_zero_values[cell.active_rows]
            nonzero_local = recovered_by_cell[cell.global_cell][1]
            zero_residual = (
                A_ii @ zero_local[interior_positions]
                + A_it @ zero_local[trace_positions]
            )
            local_rhs = active_rhs_values[cell.interior_rows]
            nonzero_residual = (
                A_ii @ nonzero_local[interior_positions]
                + A_it @ nonzero_local[trace_positions]
                - local_rhs
            )
            zero_scale = max(
                float(
                    np.max(
                        np.abs(
                            A_ii @ zero_local[interior_positions]
                        ),
                        initial=0.0,
                    )
                ),
                float(
                    np.max(
                        np.abs(A_it @ zero_local[trace_positions]),
                        initial=0.0,
                    )
                ),
                1.0,
            )
            nonzero_scale = max(
                float(np.max(np.abs(local_rhs), initial=0.0)),
                float(
                    np.max(
                        np.abs(
                            A_ii @ nonzero_local[interior_positions]
                        ),
                        initial=0.0,
                    )
                ),
                float(
                    np.max(
                        np.abs(
                            A_it @ nonzero_local[trace_positions]
                        ),
                        initial=0.0,
                    )
                ),
                1.0,
            )
            zero_equation_residual = max(
                zero_equation_residual,
                float(
                    np.max(np.abs(zero_residual), initial=0.0)
                    / zero_scale
                ),
            )
            nonzero_equation_residual = max(
                nonzero_equation_residual,
                float(
                    np.max(np.abs(nonzero_residual), initial=0.0)
                    / nonzero_scale
                ),
            )
        zero_equation_residual = float(
            mesh.comm.allreduce(zero_equation_residual, op=MPI.MAX)
        )
        nonzero_equation_residual = float(
            mesh.comm.allreduce(nonzero_equation_residual, op=MPI.MAX)
        )

        gram = sparse.csr_matrix(constraints.component_gram)
        gram_difference = gram - gram.getH()
        gram_hermitian_error = float(
            np.max(np.abs(gram_difference.data), initial=0.0)
        )
        gram_solution = sparse_linalg.spsolve(gram.tocsc(), root)
        gram_solve_residual = float(
            np.linalg.norm(gram @ gram_solution - root)
            / max(float(np.linalg.norm(root)), 1.0)
        )
        expected_primal_norm = float(
            np.sqrt(np.vdot(root, gram @ root).real)
        )
        expected_dual_norm = float(
            np.sqrt(np.vdot(root, gram_solution).real)
        )
        norm_vector = system.matrix.createVecRight()
        start, stop = norm_vector.getOwnershipRange()
        norm_vector.getArray()[:] = root[start:stop]
        norm_vector.assemble()
        observed_primal_norm = _reduced_trace_auxiliary_norm(
            system,
            norm_vector,
            trace_kind="primal",
        )
        observed_dual_norm = _reduced_trace_auxiliary_norm(
            system,
            norm_vector,
            trace_kind="dual",
        )
        primal_norm_error = abs(
            observed_primal_norm - expected_primal_norm
        ) / max(expected_primal_norm, 1.0)
        dual_norm_error = abs(
            observed_dual_norm - expected_dual_norm
        ) / max(expected_dual_norm, 1.0)

        build_audit = dict(system.build_audit)
        raw_build_audit = dict(raw_system.build_audit)
        trace_audit = dict(constraints.audit)
        routing_audit = trace_audit["owner_routed_trace_cache_audit"]
        ownership_ranges = mesh.comm.allgather(
            tuple(map(int, system.matrix.getOwnershipRange()))
        )
        ownership_closes = (
            ownership_ranges[0][0] == 0
            and ownership_ranges[-1][1]
            == constraints.independent_trace_rows
            and all(
                left_range[1] == right_range[0]
                for left_range, right_range in zip(
                    ownership_ranges[:-1],
                    ownership_ranges[1:],
                    strict=True,
                )
            )
        )
        checks = {
            "forest_pass": bool(forest.audit["pass"]),
            "carrier_pass": bool(carrier.audit["pass"]),
            "physical_trace_graph_pass": bool(authority.audit["pass"]),
            "cell_trace_binding_pass": bool(trace_audit["pass"]),
            "compiled_p6_tensor_builder": (
                build_audit["compiled_p6_tensor_builder"] is True
            ),
            "compiled_constraint_binding": (
                build_audit[
                    "compiled_trace_constraint_binding_complete"
                ]
                is True
            ),
            "compiled_owner_routing_binding": (
                build_audit[
                    "trace_constraint_owner_routing_qualified"
                ]
                is True
                and build_audit[
                    "trace_constraint_dense_global_entity_catalog_replicated"
                ]
                is False
                and build_audit[
                    "trace_constraint_distributed_scalability_qualified"
                ]
                is False
            ),
            "exact_preallocation": (
                build_audit["matrix_mallocs"] == 0
                and build_audit["matrix_nnz"]
                == build_audit["matrix_nnz_preallocated"]
            ),
            "raw_oracle_exact_preallocation": (
                raw_build_audit["matrix_mallocs"] == 0
                and raw_build_audit["matrix_nnz"]
                == raw_build_audit["matrix_nnz_preallocated"]
            ),
            "no_full_global_matrix": (
                build_audit["full_p6_global_matrix_constructed"] is False
                and build_audit[
                    "full_active_global_matrix_constructed"
                ]
                is False
            ),
            "no_slave_rows_numbered": (
                build_audit[
                    "hanging_or_floquet_slave_rows_globally_numbered"
                ]
                is False
            ),
            "primal_interior_operator_residual": (
                build_audit[
                    "interior_recovery_operator_residual_max"
                ]
                <= 5.0e-11
            ),
            "adjoint_interior_operator_residual": (
                build_audit[
                    "interior_adjoint_operator_residual_max"
                ]
                <= 5.0e-11
            ),
            "candidate_action_matches_raw_congruence": (
                action_root_rel <= 5.0e-10
                and action_probe_rel <= 5.0e-10
                and bilinear_rel <= 5.0e-10
            ),
            "right_rhs_matches_raw_congruence": right_rel <= 5.0e-10,
            "left_rhs_matches_raw_congruence": left_rel <= 5.0e-10,
            "zero_rhs_recovery_matches_raw_oracle": (
                zero_recovery_rel <= 5.0e-10
            ),
            "nonzero_rhs_recovery_matches_raw_oracle": (
                rhs_recovery_rel <= 5.0e-10
            ),
            "full_trace_recovery": trace_error <= 5.0e-11,
            "full_active_rhs_recovery_mapping": (
                local_recovery_error <= 5.0e-11
            ),
            "zero_rhs_recovered_interior_equation": (
                zero_equation_residual <= 5.0e-11
            ),
            "nonzero_rhs_recovered_interior_equation": (
                nonzero_equation_residual <= 5.0e-11
            ),
            "finite_right_reduction": bool(
                np.all(np.isfinite(right_values))
            ),
            "finite_left_reduction": bool(
                np.all(np.isfinite(left_values))
            ),
            "component_gram_hermitian": (
                gram_hermitian_error <= 5.0e-11
            ),
            "component_gram_dual_solve": (
                gram_solve_residual <= 5.0e-9
            ),
            "component_gram_primal_norm": (
                primal_norm_error <= 5.0e-11
            ),
            "component_gram_dual_norm": dual_norm_error <= 5.0e-9,
            "petsc_row_ownership_closes": ownership_closes,
            "owner_routed_trace_cache": (
                trace_audit["petsc_constraint_row_ownership_qualified"]
                is True
                and trace_audit["mpi_ghost_expansion_qualified"] is True
                and trace_audit["pde_launch_ownership_gate"] is True
                and trace_audit["full_dense_entity_catalog_replicated"]
                is False
                and routing_audit["pass"] is True
                and routing_audit[
                    "dense_global_entity_catalog_replicated"
                ]
                is False
                and routing_audit["declaration_catalog_is_metadata_only"]
                is True
                and routing_audit["request_reply_count_closes"] is True
                and all(
                    routing_audit[name] == 0
                    for name in (
                        "missing_reply_count",
                        "duplicate_reply_count",
                        "unrequested_reply_count",
                        "wrong_owner_reply_count",
                        "stale_or_corrupt_reply_count",
                    )
                )
            ),
            "owner_routed_work_partition": (
                sum(routing_audit["work_owned_block_counts_by_rank"])
                == routing_audit["declaration_count"]
                and len(
                    routing_audit[
                        "work_owned_native_array_bytes_by_rank"
                    ]
                )
                == mesh.comm.size
                and all(
                    value > 0
                    for value in routing_audit[
                        "work_owned_native_array_bytes_by_rank"
                    ]
                )
                and routing_audit[
                    "native_array_bytes_are_logical_not_rss_pss_peak"
                ]
                is True
            ),
            "cross_rank_hanging_owner_path": (
                (
                    mesh.comm.size == 1
                    and trace_audit[
                        "cross_rank_hanging_remote_participant_entity_count"
                    ]
                    == 0
                    and sum(
                        trace_audit[
                            "cross_rank_hanging_remote_lookup_counts_by_rank"
                        ]
                    )
                    == 0
                )
                or (
                    trace_audit["cross_rank_hanging_patch_count"] > 0
                    and trace_audit[
                        "cross_rank_hanging_relation_count"
                    ]
                    > 0
                    and trace_audit[
                        "cross_rank_hanging_participant_entity_count"
                    ]
                    > 0
                    and trace_audit[
                        "cross_rank_hanging_remote_participant_entity_count"
                    ]
                    > 0
                    and sum(
                        trace_audit[
                            "cross_rank_hanging_remote_lookup_counts_by_rank"
                        ]
                    )
                    > 0
                    and sum(
                        trace_audit[
                            "remote_entity_lookup_counts_by_rank"
                        ]
                    )
                    > 0
                    and all(
                        count == 0
                        for count in trace_audit[
                            "hanging_cell_ghost_counts_by_rank"
                        ]
                    )
                )
            ),
            "distributed_scalability_not_claimed": (
                trace_audit["distributed_scalability_qualified"] is False
            ),
        }
        failures = [name for name, passed in checks.items() if not passed]
        return {
            "pass": not failures,
            "status": (
                "compiled_local_h_cell_tensor_component_pass"
                if not failures
                else "compiled_local_h_cell_tensor_component_fail"
            ),
            "trace_degree": int(trace_degree),
            "cell_interior_degree": 6,
            "forest_audit": dict(forest.audit),
            "carrier_audit": dict(carrier.audit),
            "entity_map_audit": dict(entity_map.audit),
            "physical_trace_audit": dict(authority.audit),
            "cell_trace_binding_audit": trace_audit,
            "assembly_audit": build_audit,
            "raw_oracle_assembly_audit": raw_build_audit,
            "petsc_ownership_ranges": ownership_ranges,
            "stable_identity": {
                "leaf_catalog_sha256": forest.audit[
                    "leaf_catalog_sha256"
                ],
                "carrier_connectivity_sha256": carrier.audit[
                    "canonical_connectivity_sha256"
                ],
                "physical_authority_sha256": authority.audit[
                    "physical_authority_sha256"
                ],
                "flattened_graph_sha256": authority.audit[
                    "flattened_graph_sha256"
                ],
                "canonical_cell_graph_sha256": trace_audit[
                    "canonical_cell_graph_sha256"
                ],
                "owner_routed_canonical_content_sha256": routing_audit[
                    "canonical_content_sha256"
                ],
                "compiled_element_hash": build_audit[
                    "compiled_p6_element_hash"
                ],
                "active_full_rows": entity_map.active_rows,
                "raw_trace_rows": entity_map.active_trace_rows,
                "independent_trace_rows": (
                    constraints.independent_trace_rows
                ),
                "matrix_rows": build_audit["matrix_rows"],
                "matrix_nnz": build_audit["matrix_nnz"],
                "raw_oracle_matrix_rows": raw_build_audit[
                    "matrix_rows"
                ],
                "raw_oracle_matrix_nnz": raw_build_audit[
                    "matrix_nnz"
                ],
            },
            "observables": {
                "matrix_action_root": _vector_signature(action_root),
                "matrix_action_probe": _vector_signature(action_probe),
                "right_reduced_rhs": _vector_signature(right_values),
                "left_reduced_rhs": _vector_signature(left_values),
                "zero_rhs_full_recovery": _vector_signature(
                    canonical_recovered_zero_values
                ),
                "nonzero_rhs_full_recovery": _vector_signature(
                    canonical_recovered_rhs_values
                ),
                "full_recovery_signature_semantics": (
                    "oriented active cell coefficients are inverse-transformed "
                    "to reference coefficients and concatenated by canonical "
                    "forest leaf"
                ),
                "active_rhs_semantics": (
                    "trace RHS is generated from canonical physical roots; "
                    "cell-interior dual coefficients are generated by "
                    "canonical leaf/mode then transformed to DOLFINx ordering"
                ),
                "implementation_congruence_errors": {
                    "action_root_max_abs": action_root_abs,
                    "action_root_max_relative": action_root_rel,
                    "action_probe_max_abs": action_probe_abs,
                    "action_probe_max_relative": action_probe_rel,
                    "bilinear_abs": bilinear_abs,
                    "bilinear_relative": bilinear_rel,
                    "right_rhs_max_abs": right_abs,
                    "right_rhs_max_relative": right_rel,
                    "left_rhs_max_abs": left_abs,
                    "left_rhs_max_relative": left_rel,
                    "zero_rhs_recovery_max_abs": zero_recovery_abs,
                    "zero_rhs_recovery_max_relative": (
                        zero_recovery_rel
                    ),
                    "nonzero_rhs_recovery_max_abs": rhs_recovery_abs,
                    "nonzero_rhs_recovery_max_relative": (
                        rhs_recovery_rel
                    ),
                },
                "component_gram": {
                    "rows": int(gram.shape[0]),
                    "nnz": int(gram.nnz),
                    "hermitian_max_abs_error": gram_hermitian_error,
                    "dual_solve_relative_residual": gram_solve_residual,
                    "expected_primal_norm": expected_primal_norm,
                    "observed_primal_norm": observed_primal_norm,
                    "primal_norm_relative_error": primal_norm_error,
                    "expected_dual_norm": expected_dual_norm,
                    "observed_dual_norm": observed_dual_norm,
                    "dual_norm_relative_error": dual_norm_error,
                },
                "full_trace_recovery_max_abs_error": trace_error,
                "full_active_rhs_recovery_mapping_max_abs_error": (
                    local_recovery_error
                ),
                "zero_rhs_recovered_interior_equation_relative_residual": (
                    zero_equation_residual
                ),
                "nonzero_rhs_recovered_interior_equation_relative_residual": (
                    nonzero_equation_residual
                ),
            },
            "checks": checks,
            "failures": failures,
            "implementation_congruence_scope": (
                "small-fixture unconstrained p5 trace Schur using the same "
                "physical constraint map and local kernel; validates "
                "C^H S C insertion/RHS/recovery consistency, is not an "
                "independent physical-constraint oracle, is not a candidate, "
                "and is not used to claim reduced rows"
            ),
        }
    finally:
        if norm_vector is not None:
            norm_vector.destroy()
        if raw_recovered_rhs is not None:
            raw_recovered_rhs.destroy()
        if raw_recovered_zero is not None:
            raw_recovered_zero.destroy()
        if recovered_rhs is not None:
            recovered_rhs.destroy()
        if recovered_zero is not None:
            recovered_zero.destroy()
        if reduced_left is not None:
            reduced_left.destroy()
        if reduced_right is not None:
            reduced_right.destroy()
        if raw_reduced_left is not None:
            raw_reduced_left.destroy()
        if raw_reduced_right is not None:
            raw_reduced_right.destroy()
        if active_rhs is not None:
            active_rhs.destroy()
        system.destroy()
        raw_system.destroy()


def generate_authority(
    *,
    comm: MPI.Intracomm,
    source_sha: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("source SHA must be 40 lowercase hexadecimal digits")
    source_identity = _live_source_identity(
        comm,
        expected_sha=source_sha,
    )
    environment_preflight = _collective_environment_preflight(comm)
    prior_authorities = _prior_authority_manifest()
    attempt2_history = _attempt2_history_immutability_manifest()
    periodic_forest, periodic_carrier = _periodic_corner_fixture(comm)
    combined = _run_compiled_fixture(
        forest=periodic_forest,
        carrier=periodic_carrier,
        trace_degree=5,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )
    trace_resources = combined["cell_trace_binding_audit"]
    routing_resources = trace_resources["owner_routed_trace_cache_audit"]
    component_resource_ledger = {
        "semantics": "measured_or_derived_component_objects_only",
        "raw_oracle_and_candidate_co_resident": True,
        "process_peak_is_not_candidate_memory_authority": True,
        "native_array_bytes_are_logical_not_rss_pss_peak": True,
        "full_dense_entity_catalog_replicated": False,
        "replicated_entity_block_bytes_per_rank": trace_resources[
            "replicated_entity_block_bytes_per_rank"
        ],
        "unique_dolfinx_owner_entity_block_bytes_by_rank": routing_resources[
            "unique_dolfinx_owner_native_array_bytes_by_rank"
        ],
        "retained_entity_block_cache_bytes_by_rank": routing_resources[
            "local_cache_native_array_bytes_by_rank"
        ],
        "retained_entity_block_cache_bytes_global_sum": routing_resources[
            "retained_cache_native_array_bytes_global_sum"
        ],
        "retained_entity_block_cache_bytes_max": routing_resources[
            "retained_cache_native_array_bytes_max"
        ],
        "retained_entity_block_cache_duplication_factor": (
            routing_resources["retained_cache_duplication_factor"]
        ),
        "work_owned_entity_block_bytes_by_rank": routing_resources[
            "work_owned_native_array_bytes_by_rank"
        ],
        "work_owner_straddling_block_count": routing_resources[
            "work_owner_straddling_block_count"
        ],
        "outgoing_reply_logical_bytes_by_rank": routing_resources[
            "reply_native_array_bytes_by_rank"
        ],
        "incoming_reply_logical_bytes_by_rank": routing_resources[
            "received_reply_native_array_bytes_by_rank"
        ],
        "replicated_component_gram_bytes_per_rank": trace_resources[
            "replicated_component_gram_bytes_per_rank"
        ],
        "owned_cell_expansion_bytes_by_rank": trace_resources[
            "owned_cell_expansion_bytes_by_rank"
        ],
        "owned_cell_expansion_bytes_global_sum": trace_resources[
            "owned_cell_expansion_bytes_global_sum"
        ],
        "candidate_matrix_rows": combined["assembly_audit"][
            "matrix_rows"
        ],
        "candidate_matrix_nnz": combined["assembly_audit"]["matrix_nnz"],
        "diagnostic_raw_matrix_rows": combined[
            "raw_oracle_assembly_audit"
        ]["matrix_rows"],
        "diagnostic_raw_matrix_nnz": combined[
            "raw_oracle_assembly_audit"
        ]["matrix_nnz"],
        "timings_are_per_stage_mpi_max_not_rank_sum": True,
        "remote_resolution_audit_is_count_and_digest_only": trace_resources[
            "remote_resolution_audit_is_count_and_digest_only"
        ],
        "factorization_or_pde_solve_memory_measured": False,
    }
    checks = {
        "p5_trace_p6_interior_hanging_floquet": combined["pass"],
        "p5_high_condition_retained_as_risk": (
            combined["cell_trace_binding_audit"][
                "maximum_cell_expansion_condition"
            ]
            > 1.0e8
            and combined["cell_trace_binding_audit"][
                "cell_expansion_inverse_used"
            ]
            is False
        ),
        "combined_constraint_kinds": (
            combined["assembly_audit"]["trace_constraint_kinds"]
            == ["floquet", "hanging"]
        ),
        "owner_routed_pde_launch_subgate": (
            combined["cell_trace_binding_audit"][
                "pde_launch_ownership_gate"
            ]
            is True
            and combined["cell_trace_binding_audit"][
                "petsc_constraint_row_ownership_qualified"
            ]
            is True
            and combined["cell_trace_binding_audit"][
                "mpi_ghost_expansion_qualified"
            ]
            is True
        ),
        "ordinary_default_unchanged": (
            combined["assembly_audit"]["ordinary_default_changed"] is False
        ),
        "qualified_activation": (
            os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") == "1"
        ),
        "clean_live_source": source_identity[
            "verified_clean_numerical_source"
        ],
        "prior_exact_sequence_and_attempt1_hash_bound": (
            prior_authorities["phase_a_exact_sequence_hash_bound"]
            and prior_authorities[
                "attempt1_orientation_restriction_hash_bound"
            ]
        ),
        "attempt2_history_preserved": (
            attempt2_history["historical_failure_evidence_preserved"]
            is True
            and attempt2_history["history_file_count"] == 9
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "case097.local-h-attempt2-authority.v3",
        "status": (
            "local_h_attempt2_owner_routed_component_pass_mpi_gate_pending"
            if not failures
            else "local_h_attempt2_owner_routed_component_authority_fail"
        ),
        "pass": not failures,
        "source_sha": source_sha,
        "mpi_size": int(comm.size),
        "source_identity": source_identity,
        "argv": list(sys.argv),
        "fixture_config": FIXTURE_CONFIG,
        "fixture_config_sha256": _json_sha256(FIXTURE_CONFIG),
        "prior_authorities": prior_authorities,
        "attempt2_history_immutability": attempt2_history,
        "component_resource_ledger": component_resource_ledger,
        "environment": {
            "qualified_activation": os.environ.get(
                "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
            ),
            "python_executable": sys.executable,
            "dolfinx": dolfinx.__version__,
            "basix": basix.__version__,
            "petsc4py": petsc4py.__version__,
            "mpi4py": mpi4py.__version__,
            "mpi_vendor": list(MPI.get_vendor()),
            "mpi_library_version": MPI.Get_library_version().strip(),
            "rank_ids": [
                row["rank"]
                for row in environment_preflight["rank_environments"]
            ],
            "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
            "petsc_int_type": str(np.dtype(PETSc.IntType)),
            **environment_preflight,
        },
        "numerical_files": {
            str(path.relative_to(ROOT)): _sha256(path)
            for path in NUMERICAL_FILES
        },
        "p5_trace_p6_interior_hanging_floquet": combined,
        "stable_identity": combined["stable_identity"],
        "checks": checks,
        "failures": failures,
        "component_scope": (
            "actual DOLFINx cell_info + FFCx p6 cell tensor + "
            "p5 trace projection + cell-interior Schur + "
            "hanging/Floquet C_K^H S_K C_K + PETSc action/RHS/recovery"
        ),
        "distributed_scalability_qualified": False,
        "pde_launch_ownership_gate": not failures,
        "pde_launch_gate": False,
        "pde_launch_blockers": [
            "formal MPI1/MPI2/MPI8 comparison is generated separately",
            "this record is a cell-tensor component sub-gate only",
        ],
        "scalability_caveat": (
            "dense entity blocks use owner-routed retained caches, but the "
            "physical graph, component Gram, dense owned-cell expansions, and "
            "full-vector allgathers remain replicated in the fixture path"
        ),
        "heavy_pde_started": False,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }


def _signature_matches(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> bool:
    try:
        if (
            int(left["size"]) != int(right["size"])
            or list(left["sample_indices"]) != list(right["sample_indices"])
        ):
            return False
        for name in ("linf", "l2"):
            if not np.isclose(
                float(left[name]),
                float(right[name]),
                rtol=3.0e-10,
                atol=3.0e-11,
            ):
                return False
        left_scale = float(left["linf"])
        right_scale = float(right["linf"])
        if not (
            math.isfinite(left_scale)
            and math.isfinite(right_scale)
            and left_scale > 0.0
            and right_scale > 0.0
        ):
            return False
        for name in ("sum", "weighted_sum"):
            left_moment = np.asarray(left[name], dtype=np.float64)
            right_moment = np.asarray(right[name], dtype=np.float64)
            if (
                left_moment.shape != right_moment.shape
                or not np.all(np.isfinite(left_moment))
                or not np.all(np.isfinite(right_moment))
                or not np.allclose(
                    left_moment / left_scale,
                    right_moment / right_scale,
                    rtol=3.0e-10,
                    atol=3.0e-10,
                )
            ):
                return False
        left_samples = np.asarray(
            left["normalized_samples"],
            dtype=np.float64,
        )
        right_samples = np.asarray(
            right["normalized_samples"],
            dtype=np.float64,
        )
        return bool(
            left_samples.shape == right_samples.shape
            and np.all(np.isfinite(left_samples))
            and np.all(np.isfinite(right_samples))
            and np.allclose(
                left_samples,
                right_samples,
                rtol=3.0e-10,
                atol=3.0e-10,
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def _recompute_record_pass(
    payload: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    try:
        if not _all_numbers_finite(payload):
            failures.append("nonfinite_value")
        if payload["schema_version"] != (
            "case097.local-h-attempt2-authority.v3"
        ):
            failures.append("schema_version")
        if not re.fullmatch(r"[0-9a-f]{40}", str(payload["source_sha"])):
            failures.append("source_sha")
        if payload["source_identity"]["head"] != payload["source_sha"]:
            failures.append("live_head")
        if (
            payload["source_identity"][
                "verified_clean_numerical_source"
            ]
            is not True
            or payload["source_identity"]["disallowed_status_lines"]
        ):
            failures.append("clean_source")
        if (
            payload["fixture_config"] != FIXTURE_CONFIG
            or payload["fixture_config_sha256"]
            != _json_sha256(FIXTURE_CONFIG)
        ):
            failures.append("fixture_config_hash")
        if payload["prior_authorities"] != _prior_authority_manifest():
            failures.append("prior_authority_hashes")
        if payload["attempt2_history_immutability"] != (
            _attempt2_history_immutability_manifest()
        ):
            failures.append("attempt2_history_immutability")
        environment = payload["environment"]
        rank_environments = environment["rank_environments"]
        comparable_rank_environments = [
            {
                key: value
                for key, value in row.items()
                if key != "rank"
            }
            for row in rank_environments
        ]
        if (
            environment["qualified_activation"] != "1"
            or environment["petsc_scalar_type"] != "complex128"
            or environment["petsc_int_type"] != "int32"
            or environment["rank_ids"]
            != list(range(int(payload["mpi_size"])))
            or environment["all_ranks_identical"] is not True
            or len(rank_environments) != int(payload["mpi_size"])
            or any(
                row != comparable_rank_environments[0]
                for row in comparable_rank_environments[1:]
            )
        ):
            failures.append("environment")
        fixture = payload[
            "p5_trace_p6_interior_hanging_floquet"
        ]
        trace = fixture["cell_trace_binding_audit"]
        routing = trace["owner_routed_trace_cache_audit"]
        assembly = fixture["assembly_audit"]
        raw = fixture["raw_oracle_assembly_audit"]
        observables = fixture["observables"]
        if fixture["trace_degree"] != 5 or fixture[
            "cell_interior_degree"
        ] != 6:
            failures.append("degree_identity")
        if assembly["trace_constraint_kinds"] != [
            "floquet",
            "hanging",
        ]:
            failures.append("constraint_kinds")
        if not (
            fixture["forest_audit"]["pass"]
            and fixture["carrier_audit"]["pass"]
            and fixture["entity_map_audit"]["pass"]
            and fixture["physical_trace_audit"]["pass"]
            and trace["pass"]
            and assembly["pass"]
        ):
            failures.append("component_audits")
        if not (
            fixture["entity_map_audit"]["global_entity_counts"]
            == {"1": 260, "2": 170, "3": 37}
            and fixture["entity_map_audit"]["active_rows"] == 24750
            and fixture["entity_map_audit"]["active_trace_rows"] == 8100
            and fixture["physical_trace_audit"]["physical_edge_count"] == 260
            and fixture["physical_trace_audit"]["physical_face_count"] == 170
            and trace["global_cell_count"] == 37
            and trace["raw_trace_rows"] == 8100
            and trace["independent_trace_rows"] == 5430
            and assembly["matrix_rows"] == 5430
            and assembly["matrix_nnz"] == 2758850
            and raw["matrix_rows"] == 8100
            and raw["matrix_nnz"] == 3143400
        ):
            failures.append("frozen_fixture_structure")
        if not (
            trace["petsc_constraint_row_ownership_qualified"] is True
            and trace["mpi_ghost_expansion_qualified"] is True
            and trace["pde_launch_ownership_gate"] is True
            and trace["full_dense_entity_catalog_replicated"] is False
            and routing["pass"] is True
            and routing["dense_global_entity_catalog_replicated"] is False
            and routing["declaration_catalog_is_metadata_only"] is True
            and routing["request_reply_count_closes"] is True
            and sum(routing["work_owned_block_counts_by_rank"])
            == routing["declaration_count"]
            and len(routing["work_owned_native_array_bytes_by_rank"])
            == int(payload["mpi_size"])
            and all(
                value > 0
                for value in routing[
                    "work_owned_native_array_bytes_by_rank"
                ]
            )
            and all(
                routing[name] == 0
                for name in (
                    "missing_reply_count",
                    "duplicate_reply_count",
                    "unrequested_reply_count",
                    "wrong_owner_reply_count",
                    "stale_or_corrupt_reply_count",
                )
            )
        ):
            failures.append("owner_routing")
        if int(payload["mpi_size"]) > 1 and not (
            trace["cross_rank_hanging_patch_count"] > 0
            and trace["cross_rank_hanging_relation_count"] > 0
            and trace["cross_rank_hanging_participant_entity_count"] > 0
            and trace[
                "cross_rank_hanging_remote_participant_entity_count"
            ]
            > 0
            and sum(
                trace[
                    "cross_rank_hanging_remote_lookup_counts_by_rank"
                ]
            )
            > 0
            and sum(trace["remote_entity_lookup_counts_by_rank"]) > 0
            and sum(routing["request_counts_by_rank"]) > 0
            and all(
                count == 0
                for count in trace["hanging_cell_ghost_counts_by_rank"]
            )
        ):
            failures.append("cross_rank_hanging_owner_path")
        if int(payload["mpi_size"]) == 1 and not (
            trace["cross_rank_hanging_participant_entity_count"] == 0
            and trace[
                "cross_rank_hanging_remote_participant_entity_count"
            ]
            == 0
            and sum(
                trace[
                    "cross_rank_hanging_remote_lookup_counts_by_rank"
                ]
            )
            == 0
        ):
            failures.append("serial_hanging_owner_path")
        if not (
            assembly["matrix_rows"] == trace["independent_trace_rows"]
            and assembly["matrix_nnz"]
            == assembly["matrix_nnz_preallocated"]
            == assembly["matrix_nnz_allocated"]
            and assembly["matrix_mallocs"] == 0
            and raw["matrix_nnz"] == raw["matrix_nnz_preallocated"]
            == raw["matrix_nnz_allocated"]
            and raw["matrix_mallocs"] == 0
        ):
            failures.append("matrix_structure")
        if not (
            assembly["full_p6_global_matrix_constructed"] is False
            and assembly[
                "full_active_global_matrix_constructed"
            ]
            is False
            and assembly[
                "hanging_or_floquet_slave_rows_globally_numbered"
            ]
            is False
            and assembly[
                "trace_constraint_owner_routing_qualified"
            ]
            is True
            and assembly[
                "trace_constraint_dense_global_entity_catalog_replicated"
            ]
            is False
        ):
            failures.append("inactive_or_slave_rows")
        if not (
            assembly[
                "interior_recovery_operator_residual_max"
            ]
            <= 5.0e-11
            and assembly[
                "interior_adjoint_operator_residual_max"
            ]
            <= 5.0e-11
            and observables[
                "zero_rhs_recovered_interior_equation_relative_residual"
            ]
            <= 5.0e-11
            and observables[
                "nonzero_rhs_recovered_interior_equation_relative_residual"
            ]
            <= 5.0e-11
        ):
            failures.append("interior_operator_residual")
        oracle = observables["implementation_congruence_errors"]
        if any(
            float(oracle[name]) > 5.0e-10
            for name in (
                "action_root_max_relative",
                "action_probe_max_relative",
                "bilinear_relative",
                "right_rhs_max_relative",
                "left_rhs_max_relative",
                "zero_rhs_recovery_max_relative",
                "nonzero_rhs_recovery_max_relative",
            )
        ):
            failures.append("raw_oracle")
        gram = observables["component_gram"]
        if not (
            gram["rows"] == trace["independent_trace_rows"]
            and gram["hermitian_max_abs_error"] <= 5.0e-11
            and gram["dual_solve_relative_residual"] <= 5.0e-9
            and gram["primal_norm_relative_error"] <= 5.0e-11
            and gram["dual_norm_relative_error"] <= 5.0e-9
        ):
            failures.append("component_gram")
        ranges = [tuple(map(int, row)) for row in fixture[
            "petsc_ownership_ranges"
        ]]
        if not (
            len(ranges) == int(payload["mpi_size"])
            and ranges[0][0] == 0
            and ranges[-1][1] == trace["independent_trace_rows"]
            and all(
                0 <= start <= stop <= trace["independent_trace_rows"]
                for start, stop in ranges
            )
            and sum(stop - start for start, stop in ranges)
            == trace["independent_trace_rows"]
            and all(
                left[1] == right[0]
                for left, right in zip(
                    ranges[:-1],
                    ranges[1:],
                    strict=True,
                )
            )
        ):
            failures.append("petsc_ownership")
        ledger = payload["component_resource_ledger"]
        if not (
            ledger["raw_oracle_and_candidate_co_resident"] is True
            and ledger["process_peak_is_not_candidate_memory_authority"]
            is True
            and ledger["full_dense_entity_catalog_replicated"] is False
            and ledger["replicated_entity_block_bytes_per_rank"] == 0
            and ledger[
                "native_array_bytes_are_logical_not_rss_pss_peak"
            ]
            is True
            and ledger["factorization_or_pde_solve_memory_measured"]
            is False
            and ledger["retained_entity_block_cache_bytes_by_rank"]
            == routing["local_cache_native_array_bytes_by_rank"]
            and ledger["work_owned_entity_block_bytes_by_rank"]
            == routing["work_owned_native_array_bytes_by_rank"]
        ):
            failures.append("component_resource_ledger")
        if not (
            payload["distributed_scalability_qualified"] is False
            and payload["pde_launch_ownership_gate"] is True
            and payload["pde_launch_gate"] is False
            and payload["heavy_pde_started"] is False
            and payload["pde_accuracy_credit"] is False
            and payload["ordinary_default_changed"] is False
        ):
            failures.append("scope")
        if not (
            payload["pass"] is True
            and payload["failures"] == []
            and payload["status"]
            == "local_h_attempt2_owner_routed_component_pass_mpi_gate_pending"
            and fixture["pass"] is True
            and fixture["failures"] == []
        ):
            failures.append("declared_status_consistency")
        if not all(
            isinstance(digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in payload["numerical_files"].values()
        ):
            failures.append("numerical_file_hashes")
    except (KeyError, TypeError, ValueError):
        failures.append("required_fields")
    return not failures, failures


def compare_authorities(records: tuple[Path, ...]) -> dict[str, Any]:
    if len(records) != 3:
        raise ValueError("comparison requires MPI1, MPI2, and MPI8 records")
    payloads = [
        json.loads(path.read_text(encoding="utf-8")) for path in records
    ]
    mpi_sizes = {int(payload["mpi_size"]) for payload in payloads}
    source_shas = {str(payload["source_sha"]) for payload in payloads}
    live_head = subprocess.check_output(
        ("git", "rev-parse", "HEAD"),
        cwd=ROOT,
        text=True,
    ).strip()
    solver_blobs = (
        _commit_blob_manifest(next(iter(source_shas)))
        if len(source_shas) == 1
        else {}
    )
    fixture_names = ("p5_trace_p6_interior_hanging_floquet",)
    observable_names = (
        "matrix_action_root",
        "matrix_action_probe",
        "right_reduced_rhs",
        "left_reduced_rhs",
        "zero_rhs_full_recovery",
        "nonzero_rhs_full_recovery",
    )
    recomputed = [_recompute_record_pass(payload) for payload in payloads]
    expected_names = {
        1: "local_h_attempt2_mpi1_v3.json",
        2: "local_h_attempt2_mpi2_v3.json",
        8: "local_h_attempt2_mpi8_v3.json",
    }
    abi_signatures = [
        {
            key: payload["environment"]["rank_environments"][0][key]
            for key in (
                "qualified_activation",
                "python_executable",
                "dolfinx",
                "basix",
                "petsc4py",
                "mpi4py",
                "petsc_scalar_type",
                "petsc_int_type",
                "mpi_vendor",
                "mpi_library_version",
            )
        }
        for payload in payloads
    ]
    checks: dict[str, bool] = {
        "input_records_recompute_pass": all(
            passed for passed, _failures in recomputed
        ),
        "mpi_sizes_are_1_2_8": mpi_sizes == {1, 2, 8},
        "input_paths_are_case097_records": all(
            path.resolve().parent == (CASE_DIR / "records").resolve()
            and path.name
            == expected_names.get(int(payload["mpi_size"]))
            for path, payload in zip(records, payloads, strict=True)
        ),
        "same_source_sha": len(source_shas) == 1,
        "live_head_is_solver_source": (
            len(source_shas) == 1 and live_head in source_shas
        ),
        "same_numerical_file_blobs": all(
            payload["numerical_files"] == payloads[0]["numerical_files"]
            for payload in payloads[1:]
        ),
        "numerical_file_blobs_match_solver_commit": all(
            payload["numerical_files"] == solver_blobs
            for payload in payloads
        ),
        "same_fixture_config": all(
            payload["fixture_config"] == payloads[0]["fixture_config"]
            and payload["fixture_config_sha256"]
            == payloads[0]["fixture_config_sha256"]
            for payload in payloads[1:]
        ),
        "same_abi_across_mpi_runs": all(
            signature == abi_signatures[0]
            for signature in abi_signatures[1:]
        ),
        "no_heavy_pde": all(
            payload["heavy_pde_started"] is False for payload in payloads
        ),
        "no_pde_accuracy_credit": all(
            payload["pde_accuracy_credit"] is False for payload in payloads
        ),
        "no_scalability_overclaim": all(
            payload["distributed_scalability_qualified"] is False
            for payload in payloads
        ),
        "owner_routing_subgate_all_mpi": all(
            payload["pde_launch_ownership_gate"] is True
            and payload[
                "p5_trace_p6_interior_hanging_floquet"
            ]["cell_trace_binding_audit"][
                "pde_launch_ownership_gate"
            ]
            is True
            and payload[
                "p5_trace_p6_interior_hanging_floquet"
            ]["assembly_audit"][
                "trace_constraint_owner_routing_qualified"
            ]
            is True
            for payload in payloads
        ),
        "mpi2_mpi8_cross_rank_hanging_owner_path": all(
            payload[
                "p5_trace_p6_interior_hanging_floquet"
            ]["cell_trace_binding_audit"][
                "cross_rank_hanging_patch_count"
            ]
            > 0
            and payload[
                "p5_trace_p6_interior_hanging_floquet"
            ]["cell_trace_binding_audit"][
                "cross_rank_hanging_relation_count"
            ]
            > 0
            and payload[
                "p5_trace_p6_interior_hanging_floquet"
            ]["cell_trace_binding_audit"][
                "cross_rank_hanging_participant_entity_count"
            ]
            > 0
            and payload[
                "p5_trace_p6_interior_hanging_floquet"
            ]["cell_trace_binding_audit"][
                "cross_rank_hanging_remote_participant_entity_count"
            ]
            > 0
            and sum(
                payload[
                    "p5_trace_p6_interior_hanging_floquet"
                ]["cell_trace_binding_audit"][
                    "cross_rank_hanging_remote_lookup_counts_by_rank"
                ]
            )
            > 0
            for payload in payloads
            if int(payload["mpi_size"]) > 1
        ),
        "owner_routed_cache_not_full_catalog": all(
            payload[
                "p5_trace_p6_interior_hanging_floquet"
            ]["cell_trace_binding_audit"][
                "full_dense_entity_catalog_replicated"
            ]
            is False
            and payload[
                "p5_trace_p6_interior_hanging_floquet"
            ]["cell_trace_binding_audit"][
                "owner_routed_trace_cache_audit"
            ]["request_reply_count_closes"]
            is True
            for payload in payloads
        ),
    }
    digest_diagnostics: dict[str, bool] = {}
    for fixture_name in fixture_names:
        checks[f"{fixture_name}_stable_identity"] = all(
            payload[fixture_name]["stable_identity"]
            == payloads[0][fixture_name]["stable_identity"]
            for payload in payloads[1:]
        )
        for observable_name in observable_names:
            reference = payloads[0][fixture_name]["observables"][
                observable_name
            ]
            checks[
                f"{fixture_name}_{observable_name}_mpi_identity"
            ] = all(
                _signature_matches(
                    reference,
                    payload[fixture_name]["observables"][
                        observable_name
                    ],
                )
                for payload in payloads[1:]
            )
            digest_diagnostics[
                f"{fixture_name}_{observable_name}_quantized_digest_equal"
            ] = all(
                payload[fixture_name]["observables"][
                    observable_name
                ]["normalized_quantized_1e10_sha256"]
                == reference["normalized_quantized_1e10_sha256"]
                for payload in payloads[1:]
            )
        checks[f"{fixture_name}_residual_gates"] = all(
            payload[fixture_name]["assembly_audit"][
                "interior_recovery_operator_residual_max"
            ]
            <= 5.0e-11
            and payload[fixture_name]["assembly_audit"][
                "interior_adjoint_operator_residual_max"
            ]
            <= 5.0e-11
            and payload[fixture_name]["observables"][
                "full_trace_recovery_max_abs_error"
            ]
            <= 5.0e-11
            and payload[fixture_name]["observables"][
                "full_active_rhs_recovery_mapping_max_abs_error"
            ]
            <= 5.0e-11
            and payload[fixture_name]["observables"][
                "zero_rhs_recovered_interior_equation_relative_residual"
            ]
            <= 5.0e-11
            and payload[fixture_name]["observables"][
                "nonzero_rhs_recovered_interior_equation_relative_residual"
            ]
            <= 5.0e-11
            for payload in payloads
        )
        reference_gram = payloads[0][fixture_name]["observables"][
            "component_gram"
        ]
        checks[f"{fixture_name}_gram_norm_mpi_identity"] = all(
            np.allclose(
                np.asarray(
                    [
                        payload[fixture_name]["observables"][
                            "component_gram"
                        ][name]
                        for name in (
                            "expected_primal_norm",
                            "observed_primal_norm",
                            "expected_dual_norm",
                            "observed_dual_norm",
                        )
                    ],
                    dtype=np.float64,
                ),
                np.asarray(
                    [
                        reference_gram[name]
                        for name in (
                            "expected_primal_norm",
                            "observed_primal_norm",
                            "expected_dual_norm",
                            "observed_dual_norm",
                        )
                    ],
                    dtype=np.float64,
                ),
                rtol=3.0e-10,
                atol=3.0e-9,
            )
            for payload in payloads[1:]
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "case097.local-h-attempt2-mpi-comparison.v3",
        "status": (
            "local_h_attempt2_owner_routed_mpi_diagnostic_pass"
            if not failures
            else "local_h_attempt2_owner_routed_mpi_identity_fail"
        ),
        "pass": not failures,
        "source_sha": next(iter(source_shas)) if len(source_shas) == 1 else None,
        "live_head": live_head,
        "live_head_is_solver_source": (
            len(source_shas) == 1 and live_head in source_shas
        ),
        "solver_commit_numerical_files": solver_blobs,
        "mpi_sizes": sorted(mpi_sizes),
        "input_records": [
            {
                "path": f"records/{path.name}",
                "sha256": _sha256(path),
            }
            for path in records
        ],
        "input_record_recomputed_failures": {
            str(path.name): record_failures
            for path, (_passed, record_failures) in zip(
                records,
                recomputed,
                strict=True,
            )
        },
        "stable_identity": (
            payloads[0]["stable_identity"] if payloads else None
        ),
        "checks": checks,
        "non_gating_digest_diagnostics": digest_diagnostics,
        "failures": failures,
        "component_scope": (
            "one actual compiled p5-trace/p6-interior "
            "hanging+x/y-Floquet fixture with implementation-congruence "
            "raw-trace oracle"
        ),
        "distributed_scalability_qualified": False,
        "pde_launch_ownership_gate": not failures,
        "pde_launch_gate": False,
        "diagnostic_only": True,
        "independent_checker_required_for_pde_launch": True,
        "pde_launch_scope": (
            "generator comparison is diagnostic; only the source-bound "
            "independent checker may authorize a minimal local-h PDE"
        ),
        "heavy_pde_started": False,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-sha")
    parser.add_argument(
        "--compare-records",
        type=Path,
        nargs=3,
        metavar=("MPI1", "MPI2", "MPI8"),
    )
    return parser.parse_args()


def _validate_output_target(
    output: Path,
    *,
    mpi_size: int,
    comparison: bool,
) -> Path:
    resolved = output.resolve()
    if comparison:
        if (
            resolved.parent != DIAGNOSTIC_OUTPUT_DIR.resolve()
            or not resolved.name.endswith("_diagnostic.json")
        ):
            raise ValueError(
                "generator comparison output must be a *_diagnostic.json "
                "file in the Task035d /tmp diagnostic directory"
            )
    else:
        expected_name = EXPECTED_V3_RECORD_NAMES.get(int(mpi_size))
        if expected_name is None:
            raise ValueError(
                "formal Attempt2 v3 generation supports only MPI1/MPI2/MPI8"
            )
        if resolved != (RECORD_DIR / expected_name).resolve():
            raise ValueError(
                "formal Attempt2 output must match the MPI-specific v3 "
                "record path"
            )
    if output.exists():
        raise FileExistsError(
            "Attempt2 output already exists and is immutable"
        )
    return output


def main() -> int:
    args = _parse_args()
    comm = MPI.COMM_WORLD
    if args.compare_records is not None:
        if comm.size != 1:
            raise RuntimeError("record comparison must run in serial")
        output = _validate_output_target(
            args.output,
            mpi_size=comm.size,
            comparison=True,
        )
        payload = compare_authorities(tuple(args.compare_records))
    else:
        if args.source_sha is None:
            raise ValueError("--source-sha is required for generation")
        output = _validate_output_target(
            args.output,
            mpi_size=comm.size,
            comparison=False,
        )
        payload = generate_authority(
            comm=comm,
            source_sha=str(args.source_sha),
        )
    if comm.rank == 0:
        try:
            digest = _write(output, payload)
            write_envelope = {
                "ok": True,
                "error": None,
                "digest": digest,
            }
        except (OSError, TypeError, ValueError) as exc:
            write_envelope = {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "digest": None,
            }
    else:
        write_envelope = None
    write_envelope = comm.bcast(write_envelope, root=0)
    if not write_envelope["ok"]:
        raise RuntimeError(
            "collective authority write failed: "
            f"{write_envelope['error']}"
        )
    if comm.rank == 0:
        print(
            json.dumps(
                {
                    "output": str(output),
                    "sha256": write_envelope["digest"],
                    "status": payload["status"],
                    "pass": payload["pass"],
                },
                sort_keys=True,
            )
        )
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
