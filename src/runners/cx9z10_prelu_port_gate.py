"""Explicit, fail-closed CX9Z10 pre-LU BLAS8 gate.

The gate only observes already-built mesh, carrier, local factors, and
``CellPortTerms``.  A missing identity, failed comparison, or incomplete
resource preflight returns control to the existing serial assembly path.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping

import numpy as np

from src.solvers.p4_cell_condensed_inverse import (
    CX9Z10_PRELU_B8_PROFILE_ID,
    PortAssemblyExecutionDecision,
)


_PROFILE_ENV = "MYFENICS_CX9Z10_PRELU_PORT_PROFILE_ID"
_PROFILE_PATH_ENV = "MYFENICS_CX9Z10_PRELU_PROFILE_PATH"
_LAUNCHER_PATH_ENV = "MYFENICS_CX9Z10_PRELU_LAUNCHER_PATH"
_WORKER_PATH_ENV = "MYFENICS_CX9Z10_PRELU_WORKER_PATH"
_REVIEWED_PROFILE_STATE = "EXPLICIT_OPT_IN_PENDING_MAIN_PACKAGE_REVIEW"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    from src.io.resolved_config import canonical_json_bytes

    return canonical_json_bytes(value)


def _canonical_metadata_hash(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value))


def _axis_values_from_profile(target: Mapping[str, Any]) -> dict[str, tuple[float, ...]]:
    x_values: list[float] = []
    regions = target.get("x_regions_nm")
    counts = target.get("x_cells_per_region")
    if not isinstance(regions, list) or not isinstance(counts, list):
        raise ValueError("CX9Z10 profile must contain exact x regions and counts")
    if len(regions) != len(counts):
        raise ValueError("CX9Z10 x region/count lengths differ")
    for (start, stop), count in zip(regions, counts, strict=True):
        if type(count) is not int or count < 1:
            raise ValueError("CX9Z10 x region counts must be positive integers")
        segment = [float(start) + (float(stop) - float(start)) * i / count for i in range(count + 1)]
        x_values.extend(segment if not x_values else segment[1:])
    nx, ny = len(x_values) - 1, int(target["y_cells"])
    period_x, period_y = (float(item) for item in target["period_nm"])
    y_values = tuple(float(i) * period_y / ny for i in range(ny + 1))
    z_values = tuple(float(value) for value in target["z_axis_nm"])
    if nx != sum(int(item) for item in counts):
        raise ValueError("CX9Z10 target x-axis count is internally inconsistent")
    if x_values[0] != 0.0 or x_values[-1] != period_x:
        raise ValueError("CX9Z10 x regions do not span the frozen period")
    return {"x": tuple(x_values), "y": y_values, "z": z_values}


def _cell_geometry_coordinates(mesh: Any, cell: int) -> np.ndarray:
    """Return the cell's Q1 coordinates through the geometry dof map.

    Topology vertex indices and geometry coordinate indices are distinct
    namespaces in DOLFINx.  The geometry dof map is the authoritative mapping
    from a cell's local coordinate nodes to ``mesh.geometry.x``.
    """
    coordinates = np.asarray(mesh.geometry.x, dtype=np.float64)
    dofs = np.asarray(mesh.geometry.dofmap[cell], dtype=np.int64)
    if coordinates.ndim != 2 or coordinates.shape[1] != 3:
        raise ValueError("CX9Z10 geometry coordinates must have shape (N, 3)")
    if dofs.shape != (8,):
        raise ValueError(
            "CX9Z10 pre-LU mesh identity requires eight first-order hex geometry dofs"
        )
    if np.any(dofs < 0) or np.any(dofs >= len(coordinates)):
        raise ValueError("cell geometry dof map contains an out-of-range coordinate index")
    points = coordinates[dofs]
    if points.shape != (8, 3) or not np.isfinite(points).all():
        raise ValueError("cell geometry coordinates must be finite Q1 hexahedron points")
    return points


def _live_mesh_identity(mesh: Any) -> tuple[dict[str, Any], str]:
    topology = mesh.topology
    owned_cells = int(topology.index_map(3).size_local)
    local_cells: list[tuple[tuple[float, float, float], ...]] = []
    local_vertices: set[tuple[float, float, float]] = set()
    for cell in range(owned_cells):
        points = tuple(
            tuple(float(value) for value in point)
            for point in _cell_geometry_coordinates(mesh, cell)
        )
        canonical_cell = tuple(sorted(points))
        local_cells.append(canonical_cell)
        local_vertices.update(canonical_cell)
    if int(mesh.comm.size) != 1:
        raise ValueError("CX9Z10 pre-LU BLAS8 gate is qualified for MPI1 only")
    cells = sorted(local_cells)
    vertices = sorted(local_vertices)
    identity = {
        "cell_type": str(topology.cell_name()),
        "cells_global": int(topology.index_map(3).size_global),
        "vertices_global": int(topology.index_map(0).size_global),
        "geometry_shape": [len(vertices), 3],
        "canonical_connectivity_sha256": _sha256_bytes(_canonical_json(cells)),
        "canonical_geometry_sha256": _sha256_bytes(_canonical_json(vertices)),
        "axis_counts": [
            len({point[axis] for point in vertices}) for axis in range(3)
        ],
        "digest_algorithm": "sorted-cell-coordinate-metadata-v1",
    }
    return identity, _canonical_metadata_hash(identity)


class CX9Z10PreLUPortGate:
    """Capture a few live terms, compare fresh serial/BLAS8 children, then decide."""

    profile_id = CX9Z10_PRELU_B8_PROFILE_ID

    def __init__(
        self,
        *,
        profile_path: str | Path,
        launcher_path: str | Path,
        worker_path: str | Path,
        benchmark_script_path: str | Path | None = None,
        pairs: int = 3,
        warmups: int = 1,
        iterations: int = 3,
    ) -> None:
        self.profile_path = Path(profile_path).resolve()
        self.launcher_path = Path(launcher_path).resolve()
        self.worker_path = Path(worker_path).resolve()
        repository_root = Path(__file__).resolve().parents[2]
        self.benchmark_script_path = (
            Path(benchmark_script_path).resolve()
            if benchmark_script_path is not None
            else repository_root / "benchmarks" / "bench_port_terms_blas8.py"
        )
        self.pairs = int(pairs)
        self.warmups = int(warmups)
        self.iterations = int(iterations)
        self.preparation_error: str | None = None
        self._profile: dict[str, Any] | None = None
        self._profile_sha256: str | None = None
        self._benchmark: Any | None = None
        self._run_directory: Path | None = None
        self._gate_directory: Path | None = None
        self._prepared_path: Path | None = None
        self._terminal_path: Path | None = None
        self._prepared_receipt: dict[str, Any] | None = None
        self._source_sha: str | None = None
        self._worker_sha256: str | None = None
        self._launcher_sha256: str | None = None
        self._benchmark_worker_sha256: str | None = None
        self._input_sha256: str | None = None
        self._resolved_solver_profile_sha256: str | None = None
        self._resolved_profile_identity: str | None = None
        self._mesh_sha256: str | None = None
        self._mesh_identity: dict[str, Any] | None = None
        self._mesh_data: Any | None = None
        self._config: Any | None = None
        self._profile_facts: dict[str, Any] | None = None
        self._route: dict[str, Any] | None = None
        self._comparison: dict[str, Any] | None = None
        self._comparison_sha256: str | None = None
        self._carrier_mode_manifest_sha256: str | None = None
        self._decision: PortAssemblyExecutionDecision | None = None
        self._started_at = time.time()
        self._load_profile()

    def _fail_closed(self, message: str) -> None:
        if self.preparation_error is None:
            self.preparation_error = message

    def _load_profile(self) -> None:
        try:
            raw = self.profile_path.read_bytes()
            profile = json.loads(raw)
            if profile.get("schema") != "myfenics.cx9z10.prelu-port-assembly-profile.v1":
                raise ValueError("unknown CX9Z10 pre-LU profile schema")
            if profile.get("profile_id") != self.profile_id:
                raise ValueError("profile id does not match the explicit CX9Z10 opt-in")
            if profile.get("state") != _REVIEWED_PROFILE_STATE:
                raise ValueError("profile has not passed final package review")
            if profile.get("target_performance_status") != "NOT_MEASURED":
                raise ValueError("profile target-performance status must start unmeasured")
            if int(profile.get("acceptance", {}).get("fresh_numeric_children", 0)) != 6:
                raise ValueError("profile must require six fresh numeric children")
            if int(profile.get("acceptance", {}).get("paired_measurements", 0)) != 3:
                raise ValueError("profile must require three serial/BLAS8 pairs")
            self._profile = profile
            self._profile_sha256 = _sha256_bytes(raw)
        except Exception as exc:
            self._fail_closed(f"profile unavailable or unreviewed: {type(exc).__name__}: {exc}")

    def _create_run_directory(self, run_directory: str | Path) -> None:
        self._run_directory = Path(run_directory).resolve()
        self._gate_directory = self._run_directory / "prelu_port_gate"
        self._prepared_path = self._gate_directory / "prelu_gate_prepared.json"
        self._terminal_path = self._gate_directory / "prelu_gate_terminal.json"
        try:
            self._gate_directory.mkdir(parents=True, exist_ok=False)
        except Exception as exc:
            self._fail_closed(f"cannot create one-shot gate evidence directory: {type(exc).__name__}: {exc}")

    def _check_target_run(
        self,
        *,
        profile_facts: Mapping[str, Any],
        route: Mapping[str, Any],
        resolved_payload: Mapping[str, Any],
        config: Any,
    ) -> None:
        if self._profile is None:
            raise ValueError(self.preparation_error or "reviewed profile is unavailable")
        from src.io.native_capacity_profile import (
            SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z10_PROFILE,
        )

        if profile_facts.get("identity") != SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z10_PROFILE:
            raise ValueError("pre-LU BLAS8 gate is bound to a non-CX9Z10 native profile")
        if route.get("profile_identity") != SAXS_SIMPLE_GRATING_P6_DIRECT_CX9Z10_PROFILE:
            raise ValueError("pre-LU BLAS8 route identity differs from CX9Z10")
        target = self._profile["target"]
        options = profile_facts.get("component_options")
        if not isinstance(options, Mapping):
            raise ValueError("resolved profile lacks component options")
        expected_gate_profile = {
            "profile_id": self.profile_id,
            "profile_path": "profiles/cx9z10_prelu_port_blas8_v1.json",
            "activation": "exact_CX9Z10_native_profile_and_launcher_manifest",
            "numeric_lu_is_independent": True,
        }
        if options.get("pre_lu_port_assembly_gate") != expected_gate_profile:
            raise ValueError("resolved native profile lacks the exact pre-LU opt-in identity")
        expected_counts = [
            sum(int(value) for value in target["x_cells_per_region"]),
            int(target["y_cells"]),
            len(target["z_axis_nm"]) - 1,
        ]
        if list(options.get("expected_axis_cell_counts", ())) != expected_counts:
            raise ValueError("resolved profile axis counts differ from CX9Z10")
        if int(options.get("expected_global_cell_count", -1)) != int(
            target["global_hexahedra"]
        ):
            raise ValueError("resolved profile cell count differs from CX9Z10")
        modes = target["dtn_modes"]
        expected_active_count = int(modes["count"])
        expected_parent_count = int(modes["parent_count"])
        if int(route.get("active_count", -1)) != expected_active_count:
            raise ValueError("resolved active modal count differs from CX9Z10")
        if (
            int(route.get("parent_count", -1)) != expected_parent_count
            or int(route.get("expected_mode_count", -1)) != expected_parent_count
        ):
            raise ValueError("resolved parent modal count differs from CX9Z10")
        expected_parent_bounds = [
            int(modes["m"][0]),
            int(modes["m"][1]),
            int(modes["parent_n"][0]),
            int(modes["parent_n"][1]),
        ]
        if list(route.get("parent_signed_bounds_mn") or ()) != expected_parent_bounds:
            raise ValueError("resolved parent signed DtN bounds differ from CX9Z10")
        expected_bounds = [
            int(target["dtn_modes"]["m"][0]),
            int(target["dtn_modes"]["m"][1]),
            int(target["dtn_modes"]["n"][0]),
            int(target["dtn_modes"]["n"][1]),
        ]
        if list(route.get("signed_rectangle_bounds_mn") or ()) != expected_bounds:
            raise ValueError("resolved signed DtN bounds differ from CX9Z10")
        surface = options.get("surface_quadrature", {})
        volume = options.get("volume_quadrature", {})
        if int(surface.get("degree", -1)) != int(target["surface_quadrature_degree"]):
            raise ValueError("resolved surface quadrature differs from CX9Z10 q81")
        if int(volume.get("degree", -1)) != int(target["volume_quadrature_degree"]):
            raise ValueError("resolved volume quadrature differs from CX9Z10 q15")
        if str(getattr(config, "geometry_kind", "")) != "rectangular_block_grating":
            raise ValueError("resolved geometry is not the CX9Z10 rectangular grating")
        for name, expected in (
            ("period_x", target["period_nm"][0]),
            ("period_y", target["period_nm"][1]),
            ("grating_width_x", target["pillar_nm"][0]),
            ("grating_width_y", target["pillar_nm"][1]),
            ("grating_height", target["pillar_nm"][2]),
        ):
            if float(getattr(config, name)) != float(expected):
                raise ValueError(f"resolved {name} differs from CX9Z10")
        if route.get("family") != "task40_phi90":
            raise ValueError("resolved run family is not the authorized SAXS profile")
        if resolved_payload.get("derived", {}).get("native_capacity_profile", {}).get(
            "identity"
        ) != profile_facts.get("identity"):
            raise ValueError("resolved input and profile facts have different identities")

    def bind_run(
        self,
        *,
        source_sha: str | None,
        profile_facts: Mapping[str, Any],
        route: Mapping[str, Any],
        resolved_payload: Mapping[str, Any],
        config: Any,
        run_directory: str | Path,
    ) -> None:
        self._create_run_directory(run_directory)
        if self.preparation_error is not None:
            return
        try:
            if not isinstance(source_sha, str) or len(source_sha) != 40:
                raise ValueError("runtime source SHA is missing or incomplete")
            if not all(ch in "0123456789abcdef" for ch in source_sha.lower()):
                raise ValueError("runtime source SHA is not hexadecimal")
            self._check_target_run(
                profile_facts=profile_facts,
                route=route,
                resolved_payload=resolved_payload,
                config=config,
            )
            for path, label in (
                (self.worker_path, "executed worker"),
                (self.launcher_path, "authorized launcher"),
                (self.benchmark_script_path, "numeric comparison worker"),
            ):
                if not path.is_file():
                    raise FileNotFoundError(f"{label} file is unavailable: {path}")
            self._source_sha = source_sha
            self._worker_sha256 = _sha256_file(self.worker_path)
            self._launcher_sha256 = _sha256_file(self.launcher_path)
            self._benchmark_worker_sha256 = _sha256_file(self.benchmark_script_path)
            self._resolved_solver_profile_sha256 = _canonical_metadata_hash(
                dict(profile_facts)
            )
            self._resolved_profile_identity = str(profile_facts["identity"])
            self._input_sha256 = _canonical_metadata_hash(dict(resolved_payload))
            self._profile_facts = dict(profile_facts)
            self._route = dict(route)
            self._config = config
        except Exception as exc:
            self._fail_closed(f"run binding failed: {type(exc).__name__}: {exc}")

    def bind_mesh(self, *, mesh_data: Any, mesh_evidence: Mapping[str, Any]) -> None:
        if self.preparation_error is not None:
            return
        try:
            if self._profile is None or self._config is None:
                raise ValueError("profile/config were not bound before the mesh")
            if mesh_evidence.get("status") != "PASS":
                raise ValueError("live CX9Z10 mesh evidence did not pass")
            target = self._profile["target"]
            mesh = mesh_data.mesh
            identity, mesh_sha = _live_mesh_identity(mesh)
            expected_axes = _axis_values_from_profile(target)
            actual_axes = {
                axis: tuple(
                    float(value)
                    for value in np.unique(np.asarray(mesh.geometry.x)[:, index])
                )
                for index, axis in enumerate(("x", "y", "z"))
            }
            if actual_axes != expected_axes:
                raise ValueError("live mesh coordinates differ from exact CX9Z10 axes")
            expected_counts = [
                len(expected_axes[axis]) - 1 for axis in ("x", "y", "z")
            ]
            if list(mesh_evidence.get("axis_cell_counts", ())) != expected_counts:
                raise ValueError("live mesh evidence axis counts differ from CX9Z10")
            cell_count = int(mesh.topology.index_map(3).size_global)
            if cell_count != int(target["global_hexahedra"]):
                raise ValueError("live mesh cell count differs from CX9Z10")
            if identity["cell_type"] != "hexahedron":
                raise ValueError("CX9Z10 acceleration gate requires hexahedral cells")
            if int(mesh.comm.size) != int(self._profile["execution"]["mpi_size"]):
                raise ValueError("live mesh MPI size differs from the opt-in profile")
            self._mesh_identity = identity
            self._mesh_sha256 = mesh_sha
            self._mesh_data = mesh_data
        except Exception as exc:
            self._fail_closed(f"mesh binding failed: {type(exc).__name__}: {exc}")

    def _load_benchmark(self) -> Any:
        if self._benchmark is not None:
            return self._benchmark
        spec = importlib.util.spec_from_file_location(
            "_cx9z10_prelu_blas8_benchmark", self.benchmark_script_path
        )
        if spec is None or spec.loader is None:
            raise ImportError("cannot load the frozen pre-LU comparison worker")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self._benchmark = module
        return module

    def _cell_geometry_record(
        self,
        *,
        cell_index: int,
        condensed: Any,
        mesh_data: Any,
        mesh_sha256: str,
    ) -> dict[str, Any]:
        mesh = mesh_data.mesh
        topology = mesh.topology
        recovery = condensed.cell_recovery_maps[cell_index]
        class_key = tuple(recovery.class_key)
        if len(class_key) < 5:
            raise ValueError(f"cell {cell_index} raw class key is incomplete")
        tag = int(class_key[0])
        tag_names = {
            int(self._config.tags.air): "air",
            int(self._config.tags.substrate): "substrate",
            int(self._config.tags.grating): "grating",
            int(self._config.tags.top_pml): "top_pml",
            int(self._config.tags.bottom_pml): "bottom_pml",
        }
        if tag not in tag_names:
            raise ValueError(f"cell {cell_index} has unknown material tag {tag}")
        raw_widths = tuple(float(value) for value in class_key[1:4])
        if len(raw_widths) != 3 or not np.isfinite(raw_widths).all():
            raise ValueError(f"cell {cell_index} raw widths are invalid")
        points = sorted(
            tuple(float(value) for value in point)
            for point in _cell_geometry_coordinates(mesh, cell_index)
        )
        mesh_cell_count = int(topology.index_map(3).size_local)
        if len(condensed.cell_recovery_maps) != mesh_cell_count:
            raise ValueError("cell recovery order does not cover live owned mesh cells")
        return {
            "cell_id": f"mesh-cell-{cell_index}-{mesh_sha256[:16]}",
            "cell_index": int(cell_index),
            "coordinates_nm": [
                [float(value) for value in point] for point in points
            ],
            "material_label": tag_names[tag],
            "material_tag": tag,
            "raw_width_units": "nm",
            "raw_width_nm": list(raw_widths),
            "raw_width_binary64_hex": {
                axis: float(np.float64(value)).hex()
                for axis, value in zip(("x", "y", "z"), raw_widths, strict=True)
            },
            "raw_class_key": repr(class_key),
            "orientation_permutation": int(class_key[-1]),
        }

    def _persist_prepared(self, payload: dict[str, Any]) -> None:
        self._prepared_receipt = payload
        if self._prepared_path is None:
            return
        try:
            self._prepared_path.parent.mkdir(parents=True, exist_ok=True)
            with self._prepared_path.open("xb") as stream:
                stream.write((json.dumps(payload, sort_keys=True, indent=2) + "\n").encode())
                stream.flush()
                os.fsync(stream.fileno())
            directory_fd = os.open(self._prepared_path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception as exc:
            self._fail_closed(f"prepared receipt could not be persisted: {type(exc).__name__}: {exc}")

    def prepare(
        self,
        *,
        condensed: Any,
        carrier: Any,
        port_terms: Mapping[int, Any],
    ) -> PortAssemblyExecutionDecision | None:
        started = time.perf_counter()
        reason = self.preparation_error
        recommendation = "KEEP_SERIAL"
        selection: dict[str, Any] | None = None
        comparison: dict[str, Any] | None = None
        manifest: dict[str, Any] | None = None
        bundle_sha256: str | None = None
        decision: PortAssemblyExecutionDecision | None = None
        try:
            if reason is not None:
                raise ValueError(reason)
            if self._gate_directory is None or self._mesh_data is None:
                raise ValueError("run and mesh identities are not fully bound")
            if self._source_sha is None or self._profile_sha256 is None:
                raise ValueError("source/profile identities are unavailable")
            benchmark = self._load_benchmark()
            parent_threads = benchmark._blas_snapshot()
            if not parent_threads or any(
                item.get("num_threads") != 1 for item in parent_threads
            ):
                raise ValueError("parent OpenBLAS is not verified at one thread")
            inventory = benchmark._carrier_port_side_inventory(carrier)
            self._carrier_mode_manifest_sha256 = inventory[
                "port_mode_manifest_sha256"
            ]
            selected_terms, selection = benchmark._select_representative_terms(
                condensed,
                dict(port_terms),
                inventory,
                max_cells=3,
            )
            if not selection.get("coverage_sufficient"):
                raise ValueError(
                    "representative-cell coverage failed: "
                    + str(selection.get("coverage_reason"))
                )
            geometry_by_index = {
                str(index): self._cell_geometry_record(
                    cell_index=int(index),
                    condensed=condensed,
                    mesh_data=self._mesh_data,
                    mesh_sha256=self._mesh_sha256 or "",
                )
                for index in selected_terms
            }
            provenance = {
                "source_sha": self._source_sha,
                "target_profile_sha256": self._profile_sha256,
                "profile_sha256": self._profile_sha256,
                "resolved_solver_profile_sha256": self._resolved_solver_profile_sha256,
                "resolved_profile_identity": self._resolved_profile_identity,
                "input_sha256": self._input_sha256,
                "mesh_sha256": self._mesh_sha256,
                "mesh_identity": self._mesh_identity,
                "worker_sha256": self._worker_sha256,
                "launcher_sha256": self._launcher_sha256,
                "benchmark_worker_sha256": self._benchmark_worker_sha256,
                "port_mode_manifest_sha256": self._carrier_mode_manifest_sha256,
                "port_mode_indices": inventory["port_side_indices"],
                "port_mode_count": inventory["port_mode_count"],
                "ordered_mode_identity_sha256": inventory[
                    "ordered_mode_identity_sha256"
                ],
                "cell_geometry_by_index": geometry_by_index,
                "term_selection": selection,
            }
            bundle = self._gate_directory / "frozen_terms.npz"
            manifest = benchmark.freeze_live_terms(
                condensed,
                selected_terms,
                output_npz=bundle,
                provenance=provenance,
                max_cells=len(selected_terms),
            )
            bundle_sha256 = manifest["array_file_sha256"]
            comparison_directory = self._gate_directory / "comparison"
            benchmark._orchestrate(
                type(
                    "ComparisonArgs",
                    (),
                    {
                        "bundle": str(bundle),
                        "output": str(comparison_directory),
                        "pairs": self.pairs,
                        "warmups": self.warmups,
                        "iterations": self.iterations,
                    },
                )()
            )
            comparison_path = comparison_directory / "comparison.json"
            comparison = json.loads(comparison_path.read_text())
            self._comparison = comparison
            self._comparison_sha256 = _sha256_file(comparison_path)
            recommendation = str(comparison.get("recommendation", "KEEP_SERIAL"))
            if recommendation != "RECOMMEND_SCOPED_BLAS8":
                raise ValueError(f"comparison recommendation is {recommendation}")
            if self._profile is None:
                raise ValueError("reviewed opt-in profile disappeared")
            decision = PortAssemblyExecutionDecision(
                profile_id=self.profile_id,
                source_sha=self._source_sha,
                worker_sha256=str(self._worker_sha256),
                launcher_sha256=str(self._launcher_sha256),
                profile_sha256=self._profile_sha256,
                input_sha256=str(self._input_sha256),
                mesh_sha256=str(self._mesh_sha256),
                carrier_mode_manifest_sha256=self._carrier_mode_manifest_sha256,
                comparison_sha256=self._comparison_sha256,
                resolved_solver_profile_sha256=str(
                    self._resolved_solver_profile_sha256
                ),
                benchmark_worker_sha256=str(self._benchmark_worker_sha256),
                selected_cells=tuple(selection["selected"]),
                selection_coverage={
                    "sufficient": bool(selection["coverage_sufficient"]),
                    "selected_sides": list(selection["selected_sides"]),
                    "selected_class_count": int(selection["selected_class_count"]),
                },
                comparison=comparison,
                local_blas_threads=8,
            )
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            self._fail_closed(reason)
            decision = None
        payload = {
            "schema": "cx9z10.prelu_runtime_gate_prepared.v3",
            "status": "PREPARED_BLAS8" if decision is not None else "PREPARED_KEEP_SERIAL",
            "reason": None if decision is not None else reason,
            "source_sha": self._source_sha,
            "profile_sha256": self._profile_sha256,
            "resolved_solver_profile_sha256": self._resolved_solver_profile_sha256,
            "resolved_profile_identity": self._resolved_profile_identity,
            "input_sha256": self._input_sha256,
            "mesh_sha256": self._mesh_sha256,
            "carrier_mode_manifest_sha256": self._carrier_mode_manifest_sha256,
            "worker_sha256": self._worker_sha256,
            "launcher_sha256": self._launcher_sha256,
            "benchmark_worker_sha256": self._benchmark_worker_sha256,
            "selected_cells": None if selection is None else selection.get("selected"),
            "selection_coverage": None
            if selection is None
            else {
                "sufficient": selection.get("coverage_sufficient"),
                "selected_sides": selection.get("selected_sides"),
                "selected_class_count": selection.get("selected_class_count"),
                "reason": selection.get("coverage_reason"),
            },
            "captured_cells": 0 if manifest is None else manifest["selected_cell_count"],
            "bundle_sha256": bundle_sha256,
            "comparison": comparison,
            "comparison_sha256": self._comparison_sha256,
            "comparison_recommendation": recommendation,
            "same_live_matrix_reused": True,
            "no_integrals_or_carrier_recomputed": True,
            "prepared_wall_seconds": time.perf_counter() - started,
            "terminal_receipt_file": None
            if self._terminal_path is None
            else self._terminal_path.name,
        }
        self._decision = decision
        self._persist_prepared(payload)
        if self.preparation_error is not None:
            self._decision = None
            return None
        return decision

    def finish(
        self,
        *,
        decision: PortAssemblyExecutionDecision | None,
        status: str,
        assembly_call_count: int,
        assembly_started: bool,
        assembly_wall_seconds: float,
        thread_scope: Mapping[str, Any] | None,
        preparation_error: str | None,
        exception: BaseException | None,
    ) -> dict[str, Any]:
        prepared_sha = (
            _sha256_file(self._prepared_path)
            if self._prepared_path is not None and self._prepared_path.is_file()
            else None
        )
        terminal = {
            "schema": "cx9z10.prelu_runtime_gate_terminal.v3",
            "status": status,
            "prepared_receipt_sha256": prepared_sha,
            "source_sha": self._source_sha,
            "profile_sha256": self._profile_sha256,
            "resolved_solver_profile_sha256": self._resolved_solver_profile_sha256,
            "input_sha256": self._input_sha256,
            "mesh_sha256": self._mesh_sha256,
            "carrier_mode_manifest_sha256": self._carrier_mode_manifest_sha256,
            "worker_sha256": self._worker_sha256,
            "launcher_sha256": self._launcher_sha256,
            "comparison_sha256": self._comparison_sha256,
            "decision_profile_id": None if decision is None else decision.profile_id,
            "original_assemble_call_count": int(assembly_call_count),
            "original_assemble_started": bool(assembly_started),
            "original_assemble_wall_seconds": float(assembly_wall_seconds),
            "thread_scope": None if thread_scope is None else dict(thread_scope),
            "preparation_error": preparation_error or self.preparation_error,
            "exception": None
            if exception is None
            else {"type": type(exception).__name__, "message": str(exception)},
            "same_live_matrix_reused": True,
            "no_integrals_or_carrier_recomputed": True,
            "no_retry_after_original_assembler_started": True,
            "finished_unix_seconds": time.time(),
        }
        record = {"prepared": self._prepared_receipt, "terminal": terminal}
        if self._terminal_path is not None:
            try:
                self._terminal_path.parent.mkdir(parents=True, exist_ok=True)
                with self._terminal_path.open("xb") as stream:
                    stream.write((json.dumps(terminal, sort_keys=True, indent=2) + "\n").encode())
                    stream.flush()
                    os.fsync(stream.fileno())
                directory_fd = os.open(self._terminal_path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
                record["terminal_receipt_sha256"] = _sha256_file(self._terminal_path)
            except Exception as exc:
                record["terminal_receipt_error"] = f"{type(exc).__name__}: {exc}"
        return record


def pre_lu_port_gate_from_environment(
    *, required: bool = False
) -> CX9Z10PreLUPortGate | None:
    """Build the explicit gate, or a fail-closed gate for a required target."""
    requested = os.environ.get(_PROFILE_ENV)
    if requested is None and not required:
        return None
    gate = CX9Z10PreLUPortGate(
        profile_path=os.environ.get(_PROFILE_PATH_ENV, ""),
        launcher_path=os.environ.get(_LAUNCHER_PATH_ENV, ""),
        worker_path=os.environ.get(_WORKER_PATH_ENV, ""),
    )
    if requested != gate.profile_id:
        gate._fail_closed(
            f"explicit profile id {requested!r} differs from {gate.profile_id!r}"
        )
    return gate
