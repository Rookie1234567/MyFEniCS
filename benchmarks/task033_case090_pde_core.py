from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any


CASE_ID = "090_high_order_3d_floquet_hcurl"
SHARD_SCHEMA_VERSION = "task033.case090.pde-core-shard.v1"
CORE_SCHEMA_VERSION = "task033.case090.core-gates.v1"
WATCHDOG_SCHEMA_VERSION = "task033.case090.watchdog-summary.v1"
DEGREES = (1, 2, 3, 4)
MESH_TARGETS_NM = (5.0, 2.5)
MPI_SIZES = (1, 2, 4)
POLARIZATIONS = ("s", "p")
PRIMARY_GRAZING_DEG = 10.0
SMOKE_GRAZING_DEG = (1.0, 5.0)

CORE_GATE_LIMITS = {
    "constraint_round_trip_relative_error": 1.0e-12,
    "bloch_trace_mismatch": 1.0e-11,
    "reduced_full_action_relative_error": 1.0e-11,
    "full_true_residual": 1.0e-10,
    "mpi_result_difference": 1.0e-10,
}
PDE_GATE_LIMITS = {
    "full_true_residual": CORE_GATE_LIMITS["full_true_residual"],
    "bloch_trace_mismatch": CORE_GATE_LIMITS["bloch_trace_mismatch"],
    "fixture_b_port_volume_closure": 1.0e-8,
    # These are intentionally loose sanity ceilings, not claimed convergence
    # tolerances.  They prevent a merely finite but physically meaningless row
    # from qualifying while the h/p trend analysis remains the stronger test.
    "relative_field_error_hard_max": 10.0,
    "zero_order_amplitude_absolute_error_hard_max": 2.0,
}

TREND_LIMITS = {
    "h_nonincrease_relative_tolerance": 0.05,
    "h_nonincrease_absolute_tolerance": 1.0e-10,
    "p_nonregression_relative_tolerance": 0.05,
    "p4_benefit_minimum_relative": 0.01,
    "p4_setup_fraction_warning": 0.20,
    "p4_per_constrained_dof_cost_ratio_warning": 5.0,
}

NATIVE_VTU_ORACLE_METHOD = (
    "distributed rank-local VTU field oracle plus official zero-order DtN "
    "amplitude oracle"
)
NATIVE_VTU_ORACLE_REDUCTION = (
    "MPI MAX of rank-local pointwise vector-norm numerator and denominator"
)

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SourceIdentity:
    source_commit_full_sha: str | None
    tracked_source_dirty: bool
    git_error: str | None = None
    nonignored_untracked_paths: tuple[str, ...] = ()
    worktree_status_porcelain: tuple[str, ...] = ()

    def as_jsonable(self) -> dict[str, Any]:
        return {
            "source_commit_full_sha": self.source_commit_full_sha,
            "tracked_source_dirty": bool(self.tracked_source_dirty),
            "source_worktree_dirty": bool(self.tracked_source_dirty),
            "cleanliness_semantics": (
                "all tracked changes plus every nonignored untracked path"
            ),
            "nonignored_untracked_paths": list(self.nonignored_untracked_paths),
            "worktree_status_porcelain": list(self.worktree_status_porcelain),
            "git_error": self.git_error,
        }


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _payload_sha256(payload: Mapping[str, Any]) -> str:
    stripped = dict(payload)
    stripped.pop("evidence_sha256", None)
    return hashlib.sha256(_canonical_json(stripped)).hexdigest()


def attach_evidence_sha256(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result.pop("evidence_sha256", None)
    result["evidence_sha256"] = hashlib.sha256(_canonical_json(result)).hexdigest()
    return result


def evidence_sha256_is_valid(payload: Mapping[str, Any]) -> bool:
    observed = payload.get("evidence_sha256")
    return (
        isinstance(observed, str)
        and _SHA256_RE.fullmatch(observed) is not None
        and observed == _payload_sha256(payload)
    )


def inspect_tracked_source(repo_root: Path) -> SourceIdentity:
    """Return HEAD identity and complete nonignored worktree cleanliness.

    Formal records are expected to be written outside the tracked source tree or
    under an ignored artifact directory.  Git-ignored artifacts do not count,
    but every staged/unstaged tracked change and every nonignored untracked path
    does.  This prevents an uncommitted Python module from being executed under
    a formally attested commit SHA.
    """

    root = Path(repo_root).resolve()
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip().lower()
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        return SourceIdentity(None, True, f"{type(exc).__name__}: {exc}")
    if _FULL_SHA_RE.fullmatch(head) is None:
        return SourceIdentity(None, True, "git rev-parse did not return a full SHA")
    lines = tuple(line for line in status.splitlines() if line.strip())
    untracked = tuple(
        line[3:] for line in lines if line.startswith("?? ") and len(line) > 3
    )
    return SourceIdentity(head, bool(lines), None, untracked, lines)


def _h_tag(h_nm: float) -> str:
    return str(float(h_nm)).replace(".", "p")


def case_matrix_id(
    *,
    fixture: str,
    grazing_deg: float,
    polarization: str,
    degree: int,
    mesh_target_nm: float,
    mpi_size: int,
) -> str:
    fixture_tag = "a" if fixture == "fixture_a_air_box" else "b"
    return (
        f"case090_{fixture_tag}_g{float(grazing_deg):g}_{polarization}_"
        f"p{int(degree)}_h{_h_tag(mesh_target_nm)}_mpi{int(mpi_size)}"
    )


def build_shard_plan(mpi_size: int) -> list[dict[str, Any]]:
    """Return the exact 48-case PDE plan for one MPI size."""

    if int(mpi_size) not in MPI_SIZES:
        raise ValueError(f"Case090 shard MPI size must be one of {MPI_SIZES}.")
    entries: list[dict[str, Any]] = []

    def append(
        fixture: str,
        grazing_deg: float,
        degree: int,
        h_nm: float,
        polarization: str,
        requirement: str,
    ) -> None:
        entries.append(
            {
                "matrix_id": case_matrix_id(
                    fixture=fixture,
                    grazing_deg=grazing_deg,
                    polarization=polarization,
                    degree=degree,
                    mesh_target_nm=h_nm,
                    mpi_size=mpi_size,
                ),
                "fixture": fixture,
                "grazing_deg_from_surface": float(grazing_deg),
                "theta_deg_from_normal": 90.0 - float(grazing_deg),
                "polarization": polarization,
                "degree": int(degree),
                "mesh_target_nm": float(h_nm),
                "mpi_size": int(mpi_size),
                "requirement": requirement,
            }
        )

    for degree in DEGREES:
        for h_nm in MESH_TARGETS_NM:
            for polarization in POLARIZATIONS:
                append(
                    "fixture_a_air_box",
                    PRIMARY_GRAZING_DEG,
                    degree,
                    h_nm,
                    polarization,
                    "required",
                )
    for degree in DEGREES:
        for h_nm in MESH_TARGETS_NM:
            for polarization in POLARIZATIONS:
                append(
                    "fixture_b_flat_air_si",
                    PRIMARY_GRAZING_DEG,
                    degree,
                    h_nm,
                    polarization,
                    "required",
                )
    for grazing_deg in SMOKE_GRAZING_DEG:
        for degree in DEGREES:
            for polarization in POLARIZATIONS:
                append(
                    "fixture_b_flat_air_si",
                    grazing_deg,
                    degree,
                    5.0,
                    polarization,
                    "smoke",
                )

    if len(entries) != 48 or len({item["matrix_id"] for item in entries}) != 48:
        raise RuntimeError("Case090 shard plan must contain 48 unique entries.")
    return entries


def build_fixture_a_config(entry: Mapping[str, Any]):
    """Build Fixture A without importing a test module."""

    from src.common.config_3d import oblique_incidence_airbox_config

    return oblique_incidence_airbox_config(
        case_name=str(entry["matrix_id"]),
        stage_case="floquet_airbox",
        geometry_kind="airbox",
        lambda0=13.5,
        period_x=10.0,
        period_y=10.0,
        z_min=-5.0,
        z_max=5.0,
        use_floquet_xy=True,
        use_pml=False,
        incident_theta_deg=float(entry["theta_deg_from_normal"]),
        incident_phi_deg=0.0,
        polarization_kind=str(entry["polarization"]),
        custom_polarization=None,
        nedelec_degree=int(entry["degree"]),
        visualization_degree=1,
        mesh_target_size=float(entry["mesh_target_nm"]),
        mesh_cell_type="hexahedron",
        floquet_constraint_mode="auto",
        unique_output=True,
    )


def build_fixture_b_config(entry: Mapping[str, Any]):
    """Build the real flat-layer DtN Fixture B without test-module imports."""

    from src.common.config_3d import (
        NUMERICAL_SANITY_ONLY,
        SI_GRATING_INDEX_EUV_13P5_NM,
        SI_GRATING_MATERIAL_LABEL,
        SI_SUBSTRATE_INDEX_EUV_13P5_NM,
        SI_SUBSTRATE_MATERIAL_LABEL,
        normal_incidence_airbox_config,
    )

    return normal_incidence_airbox_config(
        case_name=str(entry["matrix_id"]),
        stage_case="stage4_flat_layer_sanity",
        geometry_kind="rectangular_block_grating",
        scattering_background="layered",
        stage4_boundary_model="dtn_port",
        stage4_dtn_order_policy="zero_order",
        stage4_dtn_assembly="auxiliary",
        stage4_pml_outer_bc="natural",
        lambda0=13.5,
        period_x=10.0,
        period_y=10.0,
        air_height=5.0,
        substrate_thickness=5.0,
        z_min=-5.0,
        z_max=5.0,
        interface_z=0.0,
        use_floquet_xy=True,
        use_pml=False,
        n_substrate=SI_SUBSTRATE_INDEX_EUV_13P5_NM,
        n_grating=SI_GRATING_INDEX_EUV_13P5_NM,
        substrate_material_label=SI_SUBSTRATE_MATERIAL_LABEL,
        grating_material_label=SI_GRATING_MATERIAL_LABEL,
        validation_role=NUMERICAL_SANITY_ONLY,
        grating_width_x=0.0,
        grating_width_y=0.0,
        grating_height=0.0,
        incident_theta_deg=float(entry["theta_deg_from_normal"]),
        incident_phi_deg=0.0,
        polarization_kind=str(entry["polarization"]),
        custom_polarization=None,
        nedelec_degree=int(entry["degree"]),
        visualization_degree=1,
        mesh_target_size=float(entry["mesh_target_nm"]),
        mesh_cell_type="hexahedron",
        floquet_constraint_mode="auto",
        diffraction_zero_order_only=False,
        diffraction_sample_count_x=16,
        diffraction_sample_count_y=16,
        diffraction_probe_fraction=0.5,
        diffraction_compute_modal_diagnostic=False,
        unique_output=True,
    )


def run_pde_case(entry: Mapping[str, Any], out_dir: Path) -> Mapping[str, Any]:
    """Run one real production PDE case from the Case090 matrix."""

    fixture = entry.get("fixture")
    if fixture == "fixture_a_air_box":
        from src.solvers.solve_maxwell_3d_stage_2a_floquet_airbox import (
            run_stage2a_floquet_airbox_3d_case,
        )

        return run_stage2a_floquet_airbox_3d_case(
            build_fixture_a_config(entry), Path(out_dir)
        )
    if fixture == "fixture_b_flat_air_si":
        from src.solvers.solve_maxwell_3d_stage_4a_flat_layer_sanity import (
            run_stage4a_flat_layer_sanity_3d_case,
        )

        return run_stage4a_flat_layer_sanity_3d_case(
            build_fixture_b_config(entry), Path(out_dir)
        )
    raise ValueError(f"Unknown Case090 fixture {fixture!r}.")


def _finite_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer_or_none(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _scalar_times(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, float] = {}
    for key, raw in sorted(value.items(), key=lambda item: str(item[0])):
        number = _finite_or_none(raw)
        if number is not None and number >= 0.0:
            result[str(key)] = number
    return result


def _complex_or_none(value: Any) -> complex | None:
    if isinstance(value, complex):
        result = value
    elif (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == 2
    ):
        real = _finite_or_none(value[0])
        imag = _finite_or_none(value[1])
        if real is None or imag is None:
            return None
        result = complex(real, imag)
    else:
        return None
    return result if math.isfinite(result.real) and math.isfinite(result.imag) else None


def _complex_pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _phase_error_rad(numerical: complex, expected: complex) -> float | None:
    if abs(numerical) <= 1.0e-30 or abs(expected) <= 1.0e-30:
        return None
    return float(abs(math.atan2(
        math.sin(math.atan2(numerical.imag, numerical.real) - math.atan2(expected.imag, expected.real)),
        math.cos(math.atan2(numerical.imag, numerical.real) - math.atan2(expected.imag, expected.real)),
    )))


def _amplitude_comparison(
    *, numerical: complex, analytic_interface: complex, boundary_phase: complex
) -> dict[str, Any]:
    expected = analytic_interface * boundary_phase
    absolute_error = float(abs(numerical - expected))
    return {
        "analytic_interface_amplitude": _complex_pair(analytic_interface),
        "boundary_phase": _complex_pair(boundary_phase),
        "analytic_boundary_amplitude": _complex_pair(expected),
        "numerical_outgoing_amplitude_at_boundary": _complex_pair(numerical),
        "absolute_error": absolute_error,
        "relative_error": float(absolute_error / max(abs(expected), 1.0e-14)),
        "phase_error_rad": _phase_error_rad(numerical, expected),
    }


def extract_case_artifact_validation(
    entry: Mapping[str, Any], out_dir: Path
) -> dict[str, Any]:
    """Extract independent Fixture-B field and complex-port evidence.

    Each rank reads only its own VTU shard and contributes four scalars through
    reductions.  No field, boundary vector, or point cloud is gathered.  Rank 0
    reads the small official DtN port/reference JSON files and broadcasts only
    the selected zero-order amplitudes.
    """

    if entry.get("fixture") != "fixture_b_flat_air_si":
        return {
            "status": "not_applicable",
            "method": "Fixture A uses solver-native analytic E/H errors",
            "field_errors": None,
            "zero_order_complex_amplitudes": None,
            "failures": [],
        }

    import numpy as np
    from mpi4py import MPI

    from src.common.analytic_fields_3d import (
        electric_field_code_values,
        magnetic_field_code_values,
    )

    comm = MPI.COMM_WORLD
    cfg = build_fixture_b_config(entry)
    directory = Path(out_dir)
    local_error: str | None = None
    local_metrics = {
        "E_error": 0.0,
        "E_exact": 0.0,
        "H_error": 0.0,
        "H_exact": 0.0,
        "points": 0,
    }
    try:
        import pyvista as pv

        vtu_path = (
            directory / "fields_3d_for_paraview.vtu"
            if comm.size == 1
            else directory / f"fields_3d_for_paraview_rank{comm.rank:04d}.vtu"
        )
        grid = pv.read(vtu_path)
        coords = np.asarray(grid.points, dtype=np.float64)
        e_num = np.asarray(
            grid.point_data["E_tot_V_per_m_real"], dtype=np.float64
        ) + 1j * np.asarray(
            grid.point_data["E_tot_V_per_m_imag"], dtype=np.float64
        )
        h_num = np.asarray(
            grid.point_data["H_A_per_m_real"], dtype=np.float64
        ) + 1j * np.asarray(
            grid.point_data["H_A_per_m_imag"], dtype=np.float64
        )
        if e_num.shape != (len(coords), 3) or h_num.shape != (len(coords), 3):
            raise ValueError("VTU E/H arrays are not pointwise three-vectors")
        interface_tolerance_nm = max(
            1.0e-9, 1.0e-9 * float(entry["mesh_target_nm"])
        )
        mask = np.abs(coords[:, 2] - float(cfg.interface_z)) > interface_tolerance_nm
        mask &= np.all(np.isfinite(coords), axis=1)
        if not np.any(mask):
            raise ValueError("VTU contains no finite off-interface validation points")
        coords_used = coords[mask]
        e_num = e_num[mask]
        h_num = h_num[mask]
        e_exact = (
            cfg.electric_field_scale_V_per_m
            * electric_field_code_values(cfg, coords_used)
        )
        h_exact = (
            cfg.magnetic_field_scale_A_per_m
            * magnetic_field_code_values(cfg, coords_used)
        )
        for label, numerical, exact in (
            ("E", e_num, e_exact),
            ("H", h_num, h_exact),
        ):
            error_norm = np.linalg.norm(numerical - exact, axis=1)
            exact_norm = np.linalg.norm(exact, axis=1)
            if not np.all(np.isfinite(error_norm)) or not np.all(np.isfinite(exact_norm)):
                raise ValueError(f"VTU {label} comparison contains non-finite values")
            local_metrics[f"{label}_error"] = float(np.max(error_norm))
            local_metrics[f"{label}_exact"] = float(np.max(exact_norm))
        local_metrics["points"] = int(np.count_nonzero(mask))
    except Exception as exc:
        local_error = f"rank {comm.rank}: {type(exc).__name__}: {exc}"

    rank_errors = comm.allgather(local_error)
    failures = [str(error) for error in rank_errors if error is not None]
    field_errors: dict[str, Any] | None = None
    if not failures:
        e_error = float(comm.allreduce(local_metrics["E_error"], op=MPI.MAX))
        e_exact = float(comm.allreduce(local_metrics["E_exact"], op=MPI.MAX))
        h_error = float(comm.allreduce(local_metrics["H_error"], op=MPI.MAX))
        h_exact = float(comm.allreduce(local_metrics["H_exact"], op=MPI.MAX))
        points = int(comm.allreduce(local_metrics["points"], op=MPI.SUM))
        field_errors = {
            "relative_max_abs_E_error": e_error / max(e_exact, 1.0e-30),
            "relative_max_abs_H_error": h_error / max(h_exact, 1.0e-30),
            "max_abs_E_error_V_per_m": e_error,
            "max_abs_E_exact_V_per_m": e_exact,
            "max_abs_H_error_A_per_m": h_error,
            "max_abs_H_exact_A_per_m": h_exact,
            "global_rank_local_points_compared": points,
            "interface_points_excluded": True,
            "reduction": NATIVE_VTU_ORACLE_REDUCTION,
        }
    else:
        # Keep collective ordering identical when any rank could not read its shard.
        for name in ("E_error", "E_exact", "H_error", "H_exact"):
            comm.allreduce(local_metrics[name], op=MPI.MAX)
        comm.allreduce(local_metrics["points"], op=MPI.SUM)

    amplitude_payload: dict[str, Any] | None = None
    amplitude_error: str | None = None
    if comm.rank == 0:
        try:
            port = read_json_object(directory / "port_power.json")
            reference = read_json_object(directory / "flat_layer_reference.json")
            orders = port.get("orders")
            if not isinstance(orders, list):
                raise ValueError("port_power.json has no orders array")
            polarization = str(entry["polarization"]).lower()

            def select(side: str) -> Mapping[str, Any]:
                rows = [
                    row
                    for row in orders
                    if isinstance(row, Mapping)
                    and str(row.get("side", "")).lower() == side
                    and int(row.get("m", row.get("order_m", 999))) == 0
                    and int(row.get("n", row.get("order_n", 999))) == 0
                    and str(row.get("polarization", "")).lower() == polarization
                ]
                if len(rows) != 1:
                    raise ValueError(
                        f"expected one ({side},0,0,{polarization}) DtN order, found {len(rows)}"
                    )
                return rows[0]

            top = select("top")
            bottom = select("bottom")
            r_amplitude = _complex_or_none(reference.get("r_amplitude"))
            t_amplitude = _complex_or_none(reference.get("t_amplitude"))
            top_num = _complex_or_none(top.get("outgoing_amplitude_at_boundary"))
            bottom_num = _complex_or_none(bottom.get("outgoing_amplitude_at_boundary"))
            top_phase = _complex_or_none(top.get("boundary_phase"))
            bottom_phase = _complex_or_none(bottom.get("boundary_phase"))
            if None in (
                r_amplitude,
                t_amplitude,
                top_num,
                bottom_num,
                top_phase,
                bottom_phase,
            ):
                raise ValueError("complex r/t or zero-order boundary amplitude is missing")
            incident_amplitude = complex(cfg.incident_amplitude)
            assert r_amplitude is not None and t_amplitude is not None
            assert top_num is not None and bottom_num is not None
            assert top_phase is not None and bottom_phase is not None
            amplitude_payload = {
                "status": "ok",
                "definition": (
                    "official DtN (m,n)=(0,0) outgoing_amplitude_at_boundary in "
                    "the named incident S/P basis; analytic interface Fresnel r/t "
                    "is multiplied by incident_amplitude and that row's boundary_phase"
                ),
                "source_files": ["port_power.json", "flat_layer_reference.json"],
                "reflection_top": _amplitude_comparison(
                    numerical=top_num,
                    analytic_interface=incident_amplitude * r_amplitude,
                    boundary_phase=top_phase,
                ),
                "transmission_bottom": _amplitude_comparison(
                    numerical=bottom_num,
                    analytic_interface=incident_amplitude * t_amplitude,
                    boundary_phase=bottom_phase,
                ),
            }
        except Exception as exc:
            amplitude_error = f"rank 0: {type(exc).__name__}: {exc}"
    amplitude_payload, amplitude_error = comm.bcast(
        (amplitude_payload, amplitude_error), root=0
    )
    if amplitude_error is not None:
        failures.append(amplitude_error)
    return {
        "status": "completed" if not failures else "failed",
        "method": NATIVE_VTU_ORACLE_METHOD,
        "field_errors": field_errors,
        "zero_order_complex_amplitudes": amplitude_payload,
        "failures": failures,
    }


def _expected_constraint_mode(degree: int) -> str:
    return "topological_edges_p1" if int(degree) == 1 else f"topological_trace_p{degree}"


def extract_pde_result(
    entry: Mapping[str, Any],
    summary: Mapping[str, Any],
    artifact_validation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project a solver summary into a stable, reviewable PDE evidence row."""

    degree = int(entry["degree"])
    matrix_stats = summary.get("matrix_stats")
    if not isinstance(matrix_stats, Mapping):
        matrix_stats = {}
    power_consistency = summary.get("power_consistency")
    if not isinstance(power_consistency, Mapping):
        power_consistency = {}
    residual = _finite_or_none(summary.get("linear_system_relative_residual"))
    bloch_components = {
        "x_face": _finite_or_none(summary.get("floquet_x_face_mismatch")),
        "y_face": _finite_or_none(summary.get("floquet_y_face_mismatch")),
        "edge_corner": _finite_or_none(
            summary.get("floquet_edge_corner_mismatch")
        ),
    }
    finite_bloch = [value for value in bloch_components.values() if value is not None]
    bloch_max = max(finite_bloch, default=None)
    closure = _finite_or_none(summary.get("energy_closure_error_port_volume"))
    if closure is None:
        closure = _finite_or_none(power_consistency.get("closure_error_port_volume"))
    timings = _scalar_times(summary.get("timings_seconds"))
    floquet_timings = _scalar_times(
        summary.get("floquet_constraint_timings_seconds")
    )
    artifact_fields = (
        artifact_validation.get("field_errors")
        if isinstance(artifact_validation, Mapping)
        and isinstance(artifact_validation.get("field_errors"), Mapping)
        else {}
    )
    fixture_b = entry.get("fixture") == "fixture_b_flat_air_si"
    relative_e = _finite_or_none(
        artifact_fields.get("relative_max_abs_E_error")
        if fixture_b
        else summary.get("relative_max_abs_E_error")
    )
    relative_h = _finite_or_none(
        artifact_fields.get("relative_max_abs_H_error")
        if fixture_b
        else summary.get("relative_max_abs_H_error")
    )
    amplitudes = (
        artifact_validation.get("zero_order_complex_amplitudes")
        if isinstance(artifact_validation, Mapping)
        else None
    )
    periodic_constraint = {
        "global_constraint_rows": _integer_or_none(
            summary.get("floquet_num_constraints")
        ),
        "global_constraint_nnz": _integer_or_none(
            summary.get("floquet_raw_map_nnz")
        ),
        "max_masters_per_slave": _integer_or_none(
            summary.get("floquet_max_masters_per_slave")
        ),
        "rank0_local_slaves": _integer_or_none(
            summary.get("floquet_num_local_slaves")
        ),
        "rank0_local_slave_records_seen": _integer_or_none(
            summary.get("floquet_num_local_slave_records_seen")
        ),
        "rank0_local_ghost_slave_constraints": _integer_or_none(
            summary.get("floquet_num_local_ghost_slave_constraints")
        ),
        "global_ghost_slave_constraints": _integer_or_none(
            summary.get("floquet_num_global_ghost_slave_constraints")
        ),
        "rank0_local_ghost_slave_records_skipped": _integer_or_none(
            summary.get("floquet_num_local_ghost_slave_records_skipped")
        ),
        "global_ghost_slave_records_skipped": _integer_or_none(
            summary.get("floquet_num_global_ghost_slave_records_skipped")
        ),
        "slave_edges": _integer_or_none(summary.get("floquet_num_slave_edges")),
        "matched_master_edges": _integer_or_none(
            summary.get("floquet_num_matched_master_edges")
        ),
        "slave_faces": _integer_or_none(summary.get("floquet_num_slave_faces")),
        "matched_master_faces": _integer_or_none(
            summary.get("floquet_num_matched_master_faces")
        ),
        "edge_constraint_rows": _integer_or_none(
            summary.get("floquet_num_edge_constraints")
        ),
        "face_constraint_rows": _integer_or_none(
            summary.get("floquet_num_face_constraints")
        ),
        "x_constraint_rows": _integer_or_none(
            summary.get("floquet_num_x_constraints")
        ),
        "y_constraint_rows": _integer_or_none(
            summary.get("floquet_num_y_constraints")
        ),
        "corner_constraint_rows": _integer_or_none(
            summary.get("floquet_num_corner_constraints")
        ),
        "topology_cache_hit": summary.get("floquet_topology_cache_hit"),
        "topology_cache_miss": (
            not bool(summary.get("floquet_topology_cache_hit"))
            if isinstance(summary.get("floquet_topology_cache_hit"), bool)
            else None
        ),
        "topology_build_seconds_current": _finite_or_none(
            summary.get("floquet_topology_build_seconds_current")
        ),
        "phase_update_seconds": _finite_or_none(
            summary.get("floquet_phase_update_seconds")
        ),
        "constraint_setup_outer_seconds": _finite_or_none(
            timings.get("floquet_constraint_setup_outer")
        ),
        "constraint_total_seconds": _finite_or_none(
            floquet_timings.get("floquet_total")
        ),
        "constraint_timings_seconds": floquet_timings,
        "communication_bytes_sent_current": _integer_or_none(
            summary.get("floquet_communication_bytes_sent_current")
        ),
        "communication_bytes_received_current": _integer_or_none(
            summary.get("floquet_communication_bytes_received_current")
        ),
        "rank_local_semantics_note": (
            "fields prefixed rank0_local are the root-rank values exposed by the "
            "solver summary; fields prefixed global are MPI reductions"
        ),
    }
    result: dict[str, Any] = {
        **dict(entry),
        "case_status": summary.get("case_status"),
        "official_result": summary.get("official_result"),
        "discretization": {
            "mesh_cells": _integer_or_none(summary.get("num_mesh_cells")),
            "full_nedelec_dofs": _integer_or_none(
                summary.get("num_nedelec_dofs")
            ),
            "constrained_rows": _integer_or_none(
                summary.get(
                    "constrained_linear_system_size", matrix_stats.get("matrix_rows")
                )
            ),
            "matrix_nnz": _integer_or_none(matrix_stats.get("matrix_nnz_used")),
            "constraint_rows": _integer_or_none(
                summary.get("floquet_num_constraints")
            ),
            "constraint_nnz": _integer_or_none(
                summary.get("floquet_raw_map_nnz")
            ),
            "constraint_mode": summary.get("floquet_constraint_mode_resolved"),
        },
        "algebra": {
            "full_true_residual": residual,
            "bloch_mismatch": bloch_components,
            "bloch_trace_mismatch_max": bloch_max,
            "sparse_distributed_constraints": bool(
                summary.get("floquet_num_constraints") is not None
            ),
            "global_boundary_allgather_used": summary.get(
                "floquet_used_full_boundary_gather"
            ),
            "dense_boundary_square_formed": summary.get(
                "floquet_created_dense_boundary_square"
            ),
        },
        "periodic_constraint": periodic_constraint,
        "fields": {
            "relative_max_abs_E_error": relative_e,
            "relative_max_abs_H_error": relative_h,
            "max_abs_E": _finite_or_none(summary.get("max_abs_E")),
            "max_abs_H": _finite_or_none(summary.get("max_abs_H")),
            "oracle_method": (
                artifact_validation.get("method")
                if fixture_b and isinstance(artifact_validation, Mapping)
                else "solver-native analytic exact-field comparison"
            ),
        },
        "zero_order_complex_amplitudes": amplitudes,
        "artifact_validation": (
            dict(artifact_validation)
            if isinstance(artifact_validation, Mapping)
            else None
        ),
        "power": {
            "R_total": _finite_or_none(summary.get("R_total")),
            "T_total": _finite_or_none(summary.get("T_total")),
            "R_plus_T": _finite_or_none(summary.get("R_plus_T")),
            "A_volume_total": _finite_or_none(summary.get("A_volume_total")),
            "port_volume_closure_error": closure,
            "R_port_minus_R_ref": _finite_or_none(
                power_consistency.get("R_port_minus_R_ref")
            ),
            "T_port_minus_T_ref": _finite_or_none(
                power_consistency.get("T_port_minus_T_ref")
            ),
            "A_volume_minus_A_ref": _finite_or_none(
                power_consistency.get("A_volume_minus_A_ref")
            ),
        },
        "resources": {
            "max_rank_historical_peak_rss_mb": _finite_or_none(
                summary.get("max_rss_mb")
            ),
            "sum_rank_historical_peaks_mb_upper_bound": _finite_or_none(
                summary.get("total_peak_rss_mb")
            ),
            "rss_semantics": summary.get(
                "total_peak_rss_semantics",
                "historical_rank_peaks_not_simultaneous_rss",
            ),
            "elapsed_seconds": _finite_or_none(summary.get("elapsed_seconds")),
            "timings_seconds": timings,
            "floquet_timings_seconds": floquet_timings,
        },
    }

    failures: list[str] = []
    if result["case_status"] != "completed" or result["official_result"] is not True:
        failures.append("solver did not complete as an official result")
    discretization = result["discretization"]
    for key in (
        "mesh_cells",
        "full_nedelec_dofs",
        "constrained_rows",
        "matrix_nnz",
        "constraint_rows",
        "constraint_nnz",
    ):
        if discretization[key] is None or int(discretization[key]) <= 0:
            failures.append(f"missing/nonpositive {key}")
    if discretization["constraint_mode"] != _expected_constraint_mode(degree):
        failures.append("unexpected Floquet constraint mode")
    algebra = result["algebra"]
    if residual is None or residual > PDE_GATE_LIMITS["full_true_residual"]:
        failures.append("full true residual gate failed")
    if bloch_max is None or len(finite_bloch) != 3:
        failures.append("Bloch trace mismatch is incomplete")
    elif bloch_max > PDE_GATE_LIMITS["bloch_trace_mismatch"]:
        failures.append("Bloch trace mismatch gate failed")
    if algebra["sparse_distributed_constraints"] is not True:
        failures.append("sparse distributed constraint evidence is absent")
    if algebra["global_boundary_allgather_used"] is not False:
        failures.append("global boundary allgather veto failed")
    if algebra["dense_boundary_square_formed"] is not False:
        failures.append("dense boundary square veto failed")

    required_periodic_integers = (
        "global_constraint_rows",
        "global_constraint_nnz",
        "max_masters_per_slave",
        "rank0_local_slaves",
        "rank0_local_slave_records_seen",
        "rank0_local_ghost_slave_constraints",
        "global_ghost_slave_constraints",
        "rank0_local_ghost_slave_records_skipped",
        "global_ghost_slave_records_skipped",
        "slave_edges",
        "matched_master_edges",
        "slave_faces",
        "matched_master_faces",
        "edge_constraint_rows",
        "face_constraint_rows",
        "x_constraint_rows",
        "y_constraint_rows",
        "corner_constraint_rows",
        "communication_bytes_sent_current",
        "communication_bytes_received_current",
    )
    for key in required_periodic_integers:
        if periodic_constraint[key] is None:
            failures.append(f"periodic constraint field {key} is missing")
    for key in (
        "global_constraint_rows",
        "global_constraint_nnz",
        "max_masters_per_slave",
    ):
        if periodic_constraint[key] is not None and periodic_constraint[key] <= 0:
            failures.append(f"periodic constraint field {key} is nonpositive")
    if periodic_constraint["topology_cache_hit"] not in (True, False):
        failures.append("periodic topology cache hit/miss evidence is missing")
    for key in (
        "topology_build_seconds_current",
        "phase_update_seconds",
        "constraint_setup_outer_seconds",
        "constraint_total_seconds",
    ):
        value = periodic_constraint[key]
        if value is None or value < 0.0:
            failures.append(f"periodic timing {key} is missing/nonfinite")
    if (
        periodic_constraint["slave_edges"] is not None
        and periodic_constraint["matched_master_edges"]
        != periodic_constraint["slave_edges"]
    ):
        failures.append("periodic slave/master edge counts disagree")
    if (
        periodic_constraint["slave_faces"] is not None
        and periodic_constraint["matched_master_faces"]
        != periodic_constraint["slave_faces"]
    ):
        failures.append("periodic slave/master face counts disagree")

    fields = result["fields"]
    physical_errors: list[float] = []
    for component in ("E", "H"):
        value = fields[f"relative_max_abs_{component}_error"]
        if value is None:
            failures.append(f"Fixture {'B' if fixture_b else 'A'} {component} relative error is not finite")
        else:
            physical_errors.append(value)
            if value > PDE_GATE_LIMITS["relative_field_error_hard_max"]:
                failures.append(
                    f"Fixture {'B' if fixture_b else 'A'} {component} relative error exceeds hard sanity ceiling"
                )
    if not fixture_b:
        pass
    else:
        if (
            not isinstance(artifact_validation, Mapping)
            or artifact_validation.get("status") != "completed"
        ):
            failures.append("Fixture B artifact oracle did not complete")
        if not isinstance(amplitudes, Mapping) or amplitudes.get("status") != "ok":
            failures.append("Fixture B official zero-order complex amplitude is missing")
        else:
            for channel in ("reflection_top", "transmission_bottom"):
                comparison = amplitudes.get(channel)
                if not isinstance(comparison, Mapping):
                    failures.append(f"Fixture B {channel} comparison is missing")
                    continue
                absolute_error = _finite_or_none(comparison.get("absolute_error"))
                relative_error = _finite_or_none(comparison.get("relative_error"))
                phase_error = _finite_or_none(comparison.get("phase_error_rad"))
                if None in (absolute_error, relative_error, phase_error):
                    failures.append(f"Fixture B {channel} complex error is incomplete")
                    continue
                assert absolute_error is not None
                physical_errors.append(absolute_error)
                if absolute_error > PDE_GATE_LIMITS[
                    "zero_order_amplitude_absolute_error_hard_max"
                ]:
                    failures.append(
                        f"Fixture B {channel} complex amplitude error exceeds hard sanity ceiling"
                    )
        power = result["power"]
        for key in (
            "R_total",
            "T_total",
            "R_plus_T",
            "A_volume_total",
            "port_volume_closure_error",
            "R_port_minus_R_ref",
            "T_port_minus_T_ref",
            "A_volume_minus_A_ref",
        ):
            if power[key] is None:
                failures.append(f"Fixture B {key} is not finite")
        if (
            power["port_volume_closure_error"] is not None
            and abs(power["port_volume_closure_error"])
            > PDE_GATE_LIMITS["fixture_b_port_volume_closure"]
        ):
            failures.append("Fixture B port-volume closure gate failed")
        for key in ("R_total", "T_total", "A_volume_total"):
            if power[key] is not None and power[key] < -1.0e-10:
                failures.append(f"Fixture B {key} is negative")
        for key in (
            "R_port_minus_R_ref",
            "T_port_minus_T_ref",
            "A_volume_minus_A_ref",
        ):
            if power[key] is not None:
                physical_errors.append(abs(float(power[key])))

    result["physical_error_scalar"] = max(physical_errors, default=None)
    if (
        result["physical_error_scalar"] is None
        or result["physical_error_scalar"]
        > PDE_GATE_LIMITS["relative_field_error_hard_max"]
    ):
        failures.append(
            f"Fixture {'B' if fixture_b else 'A'} combined physical error exceeds hard sanity ceiling or is missing"
        )
    result["physical_qualification_passed"] = not any(
        failure.startswith("Fixture") for failure in failures
    )
    result["numerical_gates_passed"] = not failures
    result["gate_failures"] = failures
    return result


def failed_pde_result(
    entry: Mapping[str, Any], error: str
) -> dict[str, Any]:
    return {
        **dict(entry),
        "case_status": "runner_exception",
        "official_result": False,
        "discretization": None,
        "algebra": None,
        "periodic_constraint": None,
        "fields": None,
        "zero_order_complex_amplitudes": None,
        "artifact_validation": None,
        "power": None,
        "resources": None,
        "physical_error_scalar": None,
        "physical_qualification_passed": False,
        "numerical_gates_passed": False,
        "gate_failures": [str(error)],
    }


def run_algebra_probe(
    *, degree: int, mpi_size: int, out_dir: Path
) -> dict[str, Any]:
    """Measure exact transform, trace, and true reduced/full matrix actions.

    This probe uses the production generalized constraint arrays, sparse MPC
    backsubstitution, a coercive assembled 3D H(curl) operator, MPI reductions,
    and an analytic Bloch interpolant.  It never gathers a global boundary
    vector and never forms a dense boundary square.
    """

    import numpy as np
    from basix.ufl import element
    import dolfinx_mpc
    from dolfinx import default_real_type, fem
    from dolfinx.fem import petsc as fem_petsc
    from mpi4py import MPI
    from petsc4py import PETSc
    import ufl

    from src.common.analytic_fields_3d import electric_field_code_values
    from src.common.config_3d import oblique_incidence_airbox_config
    from src.constraints.floquet_3d_high_order import (
        build_high_order_constraint_data,
    )
    from src.constraints.high_order_floquet_trace import (
        edge_coefficient_transform,
        face_coefficient_transform,
        quadrilateral_d4_vertex_permutations,
    )
    from src.geometry.mesh_builder_3d import build_airbox_mesh_3d

    comm = MPI.COMM_WORLD
    if comm.size != int(mpi_size):
        raise RuntimeError(f"MPI communicator size {comm.size} != {mpi_size}.")
    cfg = oblique_incidence_airbox_config(
        case_name=f"case090_algebra_p{degree}_mpi{mpi_size}",
        stage_case="floquet_airbox",
        geometry_kind="airbox",
        lambda0=13.5,
        period_x=10.0,
        period_y=10.0,
        z_min=0.0,
        z_max=10.0,
        use_floquet_xy=True,
        use_pml=False,
        incident_theta_deg=37.0,
        incident_phi_deg=23.0,
        polarization_kind="s",
        custom_polarization=None,
        nedelec_degree=int(degree),
        visualization_degree=1,
        mesh_target_size=5.0,
        mesh_cell_type="hexahedron",
        floquet_constraint_mode="auto",
    )
    mesh_data = build_airbox_mesh_3d(cfg, Path(out_dir))
    V = fem.functionspace(
        mesh_data.mesh,
        element(
            "N1curl",
            mesh_data.mesh.basix_cell(),
            int(degree),
            dtype=default_real_type,
        ),
    )
    data = build_high_order_constraint_data(V, mesh_data, cfg)
    # Exercise the phase-only reuse contract on the exact same mesh and space.
    # A second incident angle must update coefficients without rebuilding or
    # communicating the phase-independent periodic topology.
    phase_cfg = replace(cfg, incident_theta_deg=41.0)
    cached_phase_data = build_high_order_constraint_data(V, mesh_data, phase_cfg)
    phase_cache_probe = {
        "second_angle_deg_from_normal": 41.0,
        "topology_cache_hit": bool(cached_phase_data.topology_cache_hit),
        "topology_build_seconds_current": float(
            cached_phase_data.topology_build_seconds_current
        ),
        "phase_update_seconds": float(cached_phase_data.phase_update_seconds),
        "communication_bytes_sent_current": int(
            cached_phase_data.communication_bytes_sent_current
        ),
        "communication_bytes_received_current": int(
            cached_phase_data.communication_bytes_received_current
        ),
        "global_constraint_rows": int(cached_phase_data.global_constraint_rows),
        "global_constraint_nnz": int(cached_phase_data.global_constraint_nnz),
        "topology_rebuilt": bool(
            not cached_phase_data.topology_cache_hit
            or cached_phase_data.topology_build_seconds_current != 0.0
            or cached_phase_data.communication_bytes_sent_current != 0
            or cached_phase_data.communication_bytes_received_current != 0
        ),
    }
    mpc = dolfinx_mpc.MultiPointConstraint(V)
    mpc.add_constraint(
        V,
        data.slave_local_dofs,
        data.master_global_dofs,
        data.coefficients,
        data.master_owners,
        data.offsets,
    )
    mpc.finalize()

    transform_error = 0.0
    edge = edge_coefficient_transform(int(degree), reversed_orientation=True)
    transform_error = max(
        transform_error,
        float(np.linalg.norm(edge.conj().T @ edge - np.eye(edge.shape[0]))),
    )
    for permutation in quadrilateral_d4_vertex_permutations():
        transform = face_coefficient_transform(int(degree), permutation)
        transform_error = max(
            transform_error,
            float(
                np.linalg.norm(
                    transform.conj().T @ transform - np.eye(transform.shape[0])
                )
            ),
        )
    transform_error = float(comm.allreduce(transform_error, op=MPI.MAX))

    analytic = fem.Function(V)
    analytic.interpolate(lambda x: electric_field_code_values(cfg, x.T).T)
    analytic.x.scatter_forward()
    original_slave = np.asarray(
        analytic.x.array[np.asarray(data.slave_local_dofs, dtype=np.int32)],
        dtype=np.complex128,
    ).copy()
    mpc.homogenize(analytic)
    mpc.backsubstitution(analytic)
    reconstructed_slave = np.asarray(
        analytic.x.array[np.asarray(data.slave_local_dofs, dtype=np.int32)],
        dtype=np.complex128,
    )
    local_trace_num = float(np.vdot(
        reconstructed_slave - original_slave,
        reconstructed_slave - original_slave,
    ).real)
    local_trace_den = float(np.vdot(original_slave, original_slave).real)
    trace_num = float(comm.allreduce(local_trace_num, op=MPI.SUM))
    trace_den = float(comm.allreduce(local_trace_den, op=MPI.SUM))
    trace_error = math.sqrt(trace_num / max(trace_den, 1.0e-300))

    trial = ufl.TrialFunction(V)
    test = ufl.TestFunction(V)
    coercive_hcurl_form = (
        ufl.inner(ufl.curl(trial), ufl.curl(test))
        + ufl.inner(trial, test)
    ) * ufl.dx
    compiled_form = fem.form(coercive_hcurl_form)
    full_operator = fem_petsc.assemble_matrix(compiled_form, bcs=[])
    full_operator.assemble()
    reduced_operator = dolfinx_mpc.assemble_matrix(
        compiled_form, mpc, bcs=[]
    )
    reduced_operator.assemble()
    if full_operator.getSizes() != reduced_operator.getSizes():
        raise RuntimeError(
            "Embedded MPC operator and full H(curl) operator sizes disagree."
        )

    # C is the sparse full-space embedding of the reduced vector.  Free rows
    # are identity rows, slave rows contain the exact production constraints,
    # and slave columns are kept structurally zero.  Thus q has the ordinary
    # dolfinx_mpc embedded-reduced layout (q_slave=0), while C q is a physical
    # full vector.  This representation avoids a gathered global free-dof map.
    max_terms = max(1, int(data.max_masters_per_slave))
    prolongation = PETSc.Mat().createAIJ(
        size=full_operator.getSizes(),
        nnz=max_terms,
        comm=comm,
    )
    prolongation.setOption(PETSc.Mat.Option.NEW_NONZERO_ALLOCATION_ERR, False)
    ownership_start, ownership_end = full_operator.getOwnershipRange()
    owned_constraint_rows: dict[int, int] = {}
    for constraint_row, slave_global in enumerate(data.slave_global_dofs):
        slave = int(slave_global)
        if not ownership_start <= slave < ownership_end:
            continue
        if slave in owned_constraint_rows:
            raise RuntimeError(
                f"Owned sparse prolongation row {slave} is duplicated."
            )
        owned_constraint_rows[slave] = int(constraint_row)
    owned_constraint_count = int(
        comm.allreduce(len(owned_constraint_rows), op=MPI.SUM)
    )
    if owned_constraint_count != int(data.global_constraint_rows):
        raise RuntimeError(
            "Sparse prolongation ownership does not cover every constraint row: "
            f"owned={owned_constraint_count}, expected={data.global_constraint_rows}."
        )
    for global_row in range(ownership_start, ownership_end):
        constraint_row = owned_constraint_rows.get(global_row)
        if constraint_row is None:
            prolongation.setValue(global_row, global_row, 1.0)
            continue
        start = int(data.offsets[constraint_row])
        stop = int(data.offsets[constraint_row + 1])
        prolongation.setValues(
            [global_row],
            np.asarray(data.master_global_dofs[start:stop], dtype=PETSc.IntType),
            np.asarray(data.coefficients[start:stop], dtype=PETSc.ScalarType)[
                None, :
            ],
        )
    prolongation.assemble()

    random_reduced = full_operator.createVecRight()
    vector_start, vector_end = random_reduced.getOwnershipRange()
    global_ids = np.arange(vector_start, vector_end, dtype=np.float64) + 1.0
    random_reduced.getArray()[:] = (
        np.sin(0.173 * global_ids) + 1j * np.cos(0.319 * global_ids)
    )
    owned_slaves = np.asarray(
        sorted(owned_constraint_rows), dtype=PETSc.IntType
    )
    if len(owned_slaves):
        random_reduced.getArray()[owned_slaves - vector_start] = 0.0

    assembled_action = reduced_operator.createVecLeft()
    reduced_operator.mult(random_reduced, assembled_action)
    full_vector = full_operator.createVecRight()
    prolongation.mult(random_reduced, full_vector)
    full_action = full_operator.createVecLeft()
    full_operator.mult(full_vector, full_action)
    explicit_restricted_action = prolongation.createVecRight()
    prolongation.multHermitian(full_action, explicit_restricted_action)
    difference = assembled_action.copy()
    difference.axpy(-1.0, explicit_restricted_action)
    action_error = float(
        difference.norm()
        / max(
            assembled_action.norm(),
            explicit_restricted_action.norm(),
            1.0e-300,
        )
    )
    full_operator_type = str(full_operator.getType())
    reduced_operator_type = str(reduced_operator.getType())
    prolongation_type = str(prolongation.getType())
    full_operator_nnz = int(full_operator.getInfo()["nz_used"])
    reduced_operator_nnz = int(reduced_operator.getInfo()["nz_used"])
    prolongation_nnz = int(prolongation.getInfo()["nz_used"])
    sparse_matrix_types = all(
        "aij" in matrix_type.lower()
        for matrix_type in (
            full_operator_type,
            reduced_operator_type,
            prolongation_type,
        )
    )
    difference.destroy()
    explicit_restricted_action.destroy()
    full_action.destroy()
    full_vector.destroy()
    assembled_action.destroy()
    random_reduced.destroy()
    prolongation.destroy()
    reduced_operator.destroy()
    full_operator.destroy()

    passed = (
        transform_error
        <= CORE_GATE_LIMITS["constraint_round_trip_relative_error"]
        and trace_error <= CORE_GATE_LIMITS["bloch_trace_mismatch"]
        and action_error
        <= CORE_GATE_LIMITS["reduced_full_action_relative_error"]
        and data.global_constraint_rows > 0
        and data.global_constraint_nnz > 0
        and sparse_matrix_types
        and not data.topology.used_full_boundary_gather
        and not data.topology.created_dense_boundary_square
        and phase_cache_probe["topology_cache_hit"] is True
        and phase_cache_probe["topology_rebuilt"] is False
        and phase_cache_probe["global_constraint_rows"]
        == int(data.global_constraint_rows)
        and phase_cache_probe["global_constraint_nnz"]
        == int(data.global_constraint_nnz)
    )
    return {
        "degree": int(degree),
        "mpi_size": int(mpi_size),
        "constraint_round_trip_relative_error": transform_error,
        "bloch_trace_mismatch": trace_error,
        "reduced_full_action_relative_error": action_error,
        "constraint_rows": int(data.global_constraint_rows),
        "constraint_nnz": int(data.global_constraint_nnz),
        "phase_cache_probe": phase_cache_probe,
        "full_operator": {
            "form": "inner(curl(u),curl(v)) + inner(u,v)",
            "matrix_type": full_operator_type,
            "matrix_nnz": full_operator_nnz,
            "coercive": True,
        },
        "embedded_reduced_operator": {
            "matrix_type": reduced_operator_type,
            "matrix_nnz": reduced_operator_nnz,
            "slave_input_entries_zero": True,
        },
        "constraint_prolongation": {
            "matrix_type": prolongation_type,
            "matrix_nnz": prolongation_nnz,
            "representation": "sparse full-by-full embedding with zero slave columns",
        },
        "reduced_full_action_paths": {
            "assembled": "dolfinx_mpc assembled embedded reduced operator times q",
            "explicit": "C^H times assembled full H(curl) operator times C q",
            "random_vector": "deterministic nonzero free entries and zero slave entries",
        },
        "all_action_matrices_sparse": bool(sparse_matrix_types),
        "sparse_distributed_constraints": True,
        "global_boundary_allgather_used": bool(
            data.topology.used_full_boundary_gather
        ),
        "dense_boundary_square_formed": bool(
            data.topology.created_dense_boundary_square
        ),
        "core_algebra_gates_passed": bool(passed),
        "method": (
            "exact Basix entity-transform unitary round trip; analytic Bloch "
            "interpolant versus sparse MPC backsubstitution; true random-vector "
            "action comparison between assembled A_red q and explicit sparse "
            "C^H A_full C q for a coercive 3D H(curl) operator"
        ),
    }


def _expected_plan_ids(mpi_size: int) -> set[str]:
    return {str(item["matrix_id"]) for item in build_shard_plan(mpi_size)}


def _validate_algebra_probes(
    probes: Sequence[Mapping[str, Any]], mpi_size: int
) -> list[str]:
    problems: list[str] = []
    if len(probes) != len(DEGREES):
        problems.append("algebra probe coverage must contain exactly four degrees")
    observed: set[int] = set()
    for probe in probes:
        try:
            degree = int(probe["degree"])
            probe_mpi = int(probe["mpi_size"])
        except (KeyError, TypeError, ValueError):
            problems.append("algebra probe has invalid p/MPI identity")
            continue
        if degree not in DEGREES or degree in observed or probe_mpi != mpi_size:
            problems.append("algebra probe p/MPI coverage is duplicate or out of scope")
        observed.add(degree)
        for name in (
            "constraint_round_trip_relative_error",
            "bloch_trace_mismatch",
            "reduced_full_action_relative_error",
        ):
            value = _finite_or_none(probe.get(name))
            if value is None or value < 0.0 or value > CORE_GATE_LIMITS[name]:
                problems.append(f"p{degree} algebra gate {name} failed")
        if probe.get("core_algebra_gates_passed") is not True:
            problems.append(f"p{degree} algebra probe did not pass")
        if probe.get("all_action_matrices_sparse") is not True:
            problems.append(f"p{degree} matrix-action paths are not all sparse")
        for field, expected_form in (
            ("full_operator", "inner(curl(u),curl(v)) + inner(u,v)"),
            ("embedded_reduced_operator", None),
            ("constraint_prolongation", None),
        ):
            matrix = probe.get(field)
            if not isinstance(matrix, Mapping):
                problems.append(f"p{degree} is missing {field} evidence")
                continue
            matrix_type = matrix.get("matrix_type")
            if not isinstance(matrix_type, str) or "aij" not in matrix_type.lower():
                problems.append(f"p{degree} {field} is not a sparse AIJ matrix")
            if _integer_or_none(matrix.get("matrix_nnz")) in (None, 0):
                problems.append(f"p{degree} {field} has no positive NNZ evidence")
            if expected_form is not None and matrix.get("form") != expected_form:
                problems.append(f"p{degree} full operator form is not the qualified coercive H(curl) form")
        full_matrix = probe.get("full_operator")
        if not isinstance(full_matrix, Mapping) or full_matrix.get("coercive") is not True:
            problems.append(f"p{degree} full H(curl) operator is not marked coercive")
        reduced_matrix = probe.get("embedded_reduced_operator")
        if (
            not isinstance(reduced_matrix, Mapping)
            or reduced_matrix.get("slave_input_entries_zero") is not True
        ):
            problems.append(f"p{degree} embedded reduced input does not zero slave entries")
        prolongation = probe.get("constraint_prolongation")
        if (
            not isinstance(prolongation, Mapping)
            or prolongation.get("representation")
            != "sparse full-by-full embedding with zero slave columns"
        ):
            problems.append(f"p{degree} sparse C representation is invalid")
        paths = probe.get("reduced_full_action_paths")
        if not isinstance(paths, Mapping):
            problems.append(f"p{degree} is missing independent matrix-action paths")
        else:
            if paths.get("explicit") != (
                "C^H times assembled full H(curl) operator times C q"
            ):
                problems.append(f"p{degree} explicit C^H A C action path is absent")
            if paths.get("random_vector") != (
                "deterministic nonzero free entries and zero slave entries"
            ):
                problems.append(f"p{degree} matrix-action input is not the qualified random vector")
        if probe.get("sparse_distributed_constraints") is not True:
            problems.append(f"p{degree} sparse constraint evidence is absent")
        if probe.get("global_boundary_allgather_used") is not False:
            problems.append(f"p{degree} global boundary allgather veto failed")
        if probe.get("dense_boundary_square_formed") is not False:
            problems.append(f"p{degree} dense boundary square veto failed")
        cache_probe = probe.get("phase_cache_probe")
        if not isinstance(cache_probe, Mapping):
            problems.append(f"p{degree} phase-only topology cache probe is missing")
        else:
            if cache_probe.get("topology_cache_hit") is not True:
                problems.append(f"p{degree} phase-only topology cache did not hit")
            if cache_probe.get("topology_rebuilt") is not False:
                problems.append(f"p{degree} phase-only update rebuilt topology")
            if _finite_or_none(
                cache_probe.get("topology_build_seconds_current")
            ) != 0.0:
                problems.append(f"p{degree} cached topology build time is nonzero")
            for field in (
                "communication_bytes_sent_current",
                "communication_bytes_received_current",
            ):
                if _integer_or_none(cache_probe.get(field)) != 0:
                    problems.append(f"p{degree} cached phase update communicated topology")
            if _integer_or_none(cache_probe.get("global_constraint_rows")) != _integer_or_none(
                probe.get("constraint_rows")
            ):
                problems.append(f"p{degree} cached phase rows changed")
            if _integer_or_none(cache_probe.get("global_constraint_nnz")) != _integer_or_none(
                probe.get("constraint_nnz")
            ):
                problems.append(f"p{degree} cached phase NNZ changed")
    if observed != set(DEGREES):
        problems.append("algebra probes must cover exactly p1-p4")
    return problems


def build_shard_record(
    *,
    mpi_size: int,
    source_at_start: SourceIdentity,
    source_at_end: SourceIdentity,
    algebra_probes: Sequence[Mapping[str, Any]],
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build and hash one fail-closed MPI shard record."""

    expected_ids = _expected_plan_ids(mpi_size)
    observed_ids = [str(item.get("matrix_id", "")) for item in results]
    problems = _validate_algebra_probes(algebra_probes, mpi_size)
    if len(observed_ids) != len(set(observed_ids)):
        problems.append("PDE result matrix IDs are not unique")
    if set(observed_ids) != expected_ids or len(results) != len(expected_ids):
        problems.append(
            "PDE shard coverage is not exact: expected 48 Fixture A/B entries"
        )
    for item in results:
        if item.get("mpi_size") != int(mpi_size):
            problems.append("PDE result belongs to a different MPI shard")
        if item.get("numerical_gates_passed") is not True:
            problems.append(f"PDE numerical gates failed for {item.get('matrix_id')}")
    start_sha = source_at_start.source_commit_full_sha
    end_sha = source_at_end.source_commit_full_sha
    source_clean = (
        isinstance(start_sha, str)
        and _FULL_SHA_RE.fullmatch(start_sha) is not None
        and start_sha == end_sha
        and not source_at_start.tracked_source_dirty
        and not source_at_end.tracked_source_dirty
    )
    if not source_clean:
        problems.append("tracked source was dirty or changed during the shard run")

    payload: dict[str, Any] = {
        "schema_version": SHARD_SCHEMA_VERSION,
        "record_type": "high_order_floquet_pde_core_shard",
        "case_id": CASE_ID,
        "status": "passed" if not problems else "failed",
        "identity": {
            "is_pde_run": any(
                item.get("case_status") != "runner_exception" for item in results
            ),
            "is_solver_pass": not problems,
            "mpi_size": int(mpi_size),
            "source_commit_full_sha": start_sha,
            "source_commit_at_end_full_sha": end_sha,
            "tracked_source_dirty_at_start": source_at_start.tracked_source_dirty,
            "tracked_source_dirty_at_end": source_at_end.tracked_source_dirty,
            "source_worktree_dirty_at_start": source_at_start.tracked_source_dirty,
            "source_worktree_dirty_at_end": source_at_end.tracked_source_dirty,
            "nonignored_untracked_paths_at_start": list(
                source_at_start.nonignored_untracked_paths
            ),
            "nonignored_untracked_paths_at_end": list(
                source_at_end.nonignored_untracked_paths
            ),
            "source_cleanliness_semantics": (
                "tracked changes plus all nonignored untracked paths; ignored artifacts excluded"
            ),
            "source_clean_and_stable": source_clean,
        },
        "limits": {
            "core": dict(CORE_GATE_LIMITS),
            "pde": dict(PDE_GATE_LIMITS),
        },
        "coverage": {
            "expected_case_count": 48,
            "observed_case_count": len(results),
            "expected_matrix_ids": sorted(expected_ids),
            "observed_matrix_ids": sorted(observed_ids),
            "exact": set(observed_ids) == expected_ids
            and len(results) == len(expected_ids),
        },
        "algebra_probes": [dict(item) for item in algebra_probes],
        "pde_results": [dict(item) for item in results],
        "failures": problems,
    }
    return attach_evidence_sha256(payload)


def validate_shard_record(record: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    if record.get("schema_version") != SHARD_SCHEMA_VERSION:
        problems.append("wrong shard schema_version")
    if record.get("record_type") != "high_order_floquet_pde_core_shard":
        problems.append("wrong shard record_type")
    if record.get("case_id") != CASE_ID:
        problems.append("wrong shard case_id")
    identity = record.get("identity")
    if not isinstance(identity, Mapping):
        return problems + ["missing shard identity"]
    mpi_size = identity.get("mpi_size")
    if type(mpi_size) is not int or mpi_size not in MPI_SIZES:
        return problems + ["invalid shard MPI size"]
    if not evidence_sha256_is_valid(record):
        problems.append("invalid shard evidence_sha256")
    source_sha = identity.get("source_commit_full_sha")
    if not isinstance(source_sha, str) or _FULL_SHA_RE.fullmatch(source_sha) is None:
        problems.append("invalid shard source SHA")
    if identity.get("source_clean_and_stable") is not True:
        problems.append("shard source was not clean and stable")
    if (
        identity.get("source_worktree_dirty_at_start") is not False
        or identity.get("source_worktree_dirty_at_end") is not False
        or identity.get("nonignored_untracked_paths_at_start") != []
        or identity.get("nonignored_untracked_paths_at_end") != []
    ):
        problems.append("shard source includes tracked or nonignored untracked changes")
    results = record.get("pde_results")
    if not isinstance(results, list):
        problems.append("shard pde_results must be a list")
        results = []
    ids = [str(item.get("matrix_id", "")) for item in results if isinstance(item, Mapping)]
    if len(ids) != len(results) or len(ids) != len(set(ids)):
        problems.append("shard result rows are invalid or duplicated")
    if set(ids) != _expected_plan_ids(mpi_size) or len(results) != 48:
        problems.append("shard result coverage is not exactly 48 entries")
    if any(
        not isinstance(item, Mapping)
        or item.get("numerical_gates_passed") is not True
        for item in results
    ):
        problems.append("one or more shard PDE numerical gates failed")
    for item in results:
        if not isinstance(item, Mapping):
            continue
        if item.get("physical_qualification_passed") is not True:
            problems.append("one or more shard physical qualifications failed")
        physical_error = _finite_or_none(item.get("physical_error_scalar"))
        if physical_error is None or not 0.0 <= physical_error <= PDE_GATE_LIMITS[
            "relative_field_error_hard_max"
        ]:
            problems.append("one or more shard physical error scalars are invalid")
        periodic = item.get("periodic_constraint")
        if not isinstance(periodic, Mapping):
            problems.append("one or more shard periodic constraint records are missing")
            continue
        for name in (
            "global_constraint_rows",
            "global_constraint_nnz",
            "max_masters_per_slave",
            "communication_bytes_sent_current",
            "communication_bytes_received_current",
        ):
            if _integer_or_none(periodic.get(name)) is None:
                problems.append(f"one or more shard periodic {name} fields are missing")
        if periodic.get("topology_cache_hit") not in (True, False):
            problems.append("one or more shard topology cache fields are missing")
    probes = record.get("algebra_probes")
    if not isinstance(probes, list):
        problems.append("shard algebra_probes must be a list")
    else:
        problems.extend(_validate_algebra_probes(probes, mpi_size))
    if record.get("status") != ("passed" if not problems else "failed"):
        problems.append("shard status is inconsistent with its evidence")
    return problems


_FIXTURE_A_MPI_PATHS = (
    ("algebra", "full_true_residual"),
    ("algebra", "bloch_trace_mismatch_max"),
    ("fields", "relative_max_abs_E_error"),
    ("fields", "relative_max_abs_H_error"),
    ("periodic_constraint", "global_constraint_rows"),
    ("periodic_constraint", "global_constraint_nnz"),
    ("periodic_constraint", "max_masters_per_slave"),
)
_FIXTURE_B_MPI_PATHS = (
    ("algebra", "full_true_residual"),
    ("algebra", "bloch_trace_mismatch_max"),
    ("fields", "relative_max_abs_E_error"),
    ("fields", "relative_max_abs_H_error"),
    ("fields", "max_abs_E"),
    ("fields", "max_abs_H"),
    ("zero_order_complex_amplitudes", "reflection_top", "absolute_error"),
    ("zero_order_complex_amplitudes", "reflection_top", "relative_error"),
    ("zero_order_complex_amplitudes", "reflection_top", "phase_error_rad"),
    ("zero_order_complex_amplitudes", "transmission_bottom", "absolute_error"),
    ("zero_order_complex_amplitudes", "transmission_bottom", "relative_error"),
    ("zero_order_complex_amplitudes", "transmission_bottom", "phase_error_rad"),
    ("power", "R_total"),
    ("power", "T_total"),
    ("power", "R_plus_T"),
    ("power", "A_volume_total"),
    ("power", "port_volume_closure_error"),
    ("power", "R_port_minus_R_ref"),
    ("power", "T_port_minus_T_ref"),
    ("power", "A_volume_minus_A_ref"),
    ("periodic_constraint", "global_constraint_rows"),
    ("periodic_constraint", "global_constraint_nnz"),
    ("periodic_constraint", "max_masters_per_slave"),
)

_FIXTURE_B_MPI_COMPLEX_PATHS = (
    (
        "zero_order_complex_amplitudes",
        "reflection_top",
        "numerical_outgoing_amplitude_at_boundary",
    ),
    (
        "zero_order_complex_amplitudes",
        "transmission_bottom",
        "numerical_outgoing_amplitude_at_boundary",
    ),
)


def _case_key_without_mpi(item: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        item.get("fixture"),
        item.get("grazing_deg_from_surface"),
        item.get("polarization"),
        item.get("degree"),
        item.get("mesh_target_nm"),
        item.get("requirement"),
    )


def _nested_value(item: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = item
    for name in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(name)
    return current


def _nested_number(item: Mapping[str, Any], path: Sequence[str]) -> float | None:
    return _finite_or_none(_nested_value(item, path))


def _nested_complex(item: Mapping[str, Any], path: Sequence[str]) -> complex | None:
    current: Any = item
    for name in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(name)
    return _complex_or_none(current)


def compute_mpi_result_difference(
    shards: Sequence[Mapping[str, Any]],
) -> tuple[float | None, list[str]]:
    """Compare all rank-independent numerical outputs across MPI1/2/4."""

    problems: list[str] = []
    by_key: dict[tuple[Any, ...], dict[int, Mapping[str, Any]]] = {}
    for shard in shards:
        identity = shard.get("identity")
        mpi_size = identity.get("mpi_size") if isinstance(identity, Mapping) else None
        results = shard.get("pde_results")
        if type(mpi_size) is not int or not isinstance(results, list):
            problems.append("cannot compare MPI results from malformed shard")
            continue
        for item in results:
            if not isinstance(item, Mapping):
                problems.append("cannot compare a non-object PDE result")
                continue
            key = _case_key_without_mpi(item)
            by_key.setdefault(key, {})[mpi_size] = item

    maximum = 0.0
    for key, variants in sorted(by_key.items(), key=lambda pair: repr(pair[0])):
        if set(variants) != set(MPI_SIZES):
            problems.append(f"MPI comparison coverage missing for case key {key!r}")
            continue
        fixture = key[0]
        paths = (
            _FIXTURE_A_MPI_PATHS
            if fixture == "fixture_a_air_box"
            else _FIXTURE_B_MPI_PATHS
        )
        for path in paths:
            values = [_nested_number(variants[size], path) for size in MPI_SIZES]
            if any(value is None for value in values):
                problems.append(
                    f"MPI comparison field {'.'.join(path)} is missing for {key!r}"
                )
                continue
            finite_values = [float(value) for value in values if value is not None]
            scale = max(1.0, *(abs(value) for value in finite_values))
            difference = (
                max(finite_values) - min(finite_values)
            ) / scale
            maximum = max(maximum, abs(float(difference)))
        if fixture == "fixture_b_flat_air_si":
            for path in _FIXTURE_B_MPI_COMPLEX_PATHS:
                values = [_nested_complex(variants[size], path) for size in MPI_SIZES]
                if any(value is None for value in values):
                    problems.append(
                        f"MPI complex field {'.'.join(path)} is missing for {key!r}"
                    )
                    continue
                finite_values = [complex(value) for value in values if value is not None]
                scale = max(1.0, *(abs(value) for value in finite_values))
                difference = max(
                    abs(first - second)
                    for first in finite_values
                    for second in finite_values
                ) / scale
                maximum = max(maximum, float(difference))
    expected_case_keys = 48
    if len(by_key) != expected_case_keys:
        problems.append(
            f"MPI comparison requires {expected_case_keys} case keys, found {len(by_key)}"
        )
    return (None if problems else maximum), problems


def validate_watchdog_summary(
    record: Mapping[str, Any],
    *,
    expected_mpi_size: int | None = None,
    expected_source_sha: str | None = None,
) -> list[str]:
    """Validate one external shard-watchdog summary without trusting status."""

    problems: list[str] = []
    if record.get("schema_version") != WATCHDOG_SCHEMA_VERSION:
        problems.append("wrong watchdog schema_version")
    if record.get("record_type") != "external_shard_memory_watchdog":
        problems.append("wrong watchdog record_type")
    if record.get("case_id") != CASE_ID:
        problems.append("wrong watchdog case_id")
    if not evidence_sha256_is_valid(record):
        problems.append("invalid watchdog evidence_sha256")
    identity = record.get("identity")
    if not isinstance(identity, Mapping):
        return problems + ["missing watchdog identity"]
    mpi_size = identity.get("mpi_size")
    if type(mpi_size) is not int or mpi_size not in MPI_SIZES:
        problems.append("invalid watchdog MPI size")
    if expected_mpi_size is not None and mpi_size != int(expected_mpi_size):
        problems.append("watchdog MPI size does not match its shard")
    source_sha = identity.get("source_commit_full_sha")
    if not isinstance(source_sha, str) or _FULL_SHA_RE.fullmatch(source_sha) is None:
        problems.append("invalid watchdog source SHA")
    if expected_source_sha is not None and source_sha != expected_source_sha:
        problems.append("watchdog source SHA does not match shard source SHA")
    if identity.get("source_clean_and_stable") is not True:
        problems.append("watchdog source was not clean and stable")
    if (
        identity.get("source_worktree_dirty_at_start") is not False
        or identity.get("source_worktree_dirty_at_end") is not False
        or identity.get("nonignored_untracked_paths_at_start") != []
        or identity.get("nonignored_untracked_paths_at_end") != []
    ):
        problems.append(
            "watchdog source includes tracked or nonignored untracked changes"
        )
    worker = record.get("worker")
    if (
        not isinstance(worker, Mapping)
        or worker.get("launched") is not True
        or worker.get("exit_code") != 0
    ):
        problems.append("watchdog worker did not exit successfully")
    preflight = record.get("preflight")
    if not isinstance(preflight, Mapping):
        problems.append("watchdog preflight evidence is missing")
    else:
        if preflight.get("passed") is not True:
            problems.append("watchdog preflight did not pass")
        if preflight.get("cgroup_memory_limit_state") != "finite":
            problems.append("watchdog container limit is not finite/readable")
        limit = _integer_or_none(preflight.get("cgroup_memory_limit_bytes"))
        host_available = _integer_or_none(
            preflight.get("host_available_memory_bytes")
        )
        cgroup_current = _integer_or_none(
            preflight.get("cgroup_memory_current_bytes")
        )
        swap_current = _integer_or_none(preflight.get("swap_current_bytes"))
        effective = _integer_or_none(preflight.get("effective_memory_bytes"))
        warning_threshold = _integer_or_none(
            preflight.get("warning_threshold_bytes")
        )
        termination_threshold = _integer_or_none(
            preflight.get("termination_threshold_bytes")
        )
        if None in (limit, host_available, cgroup_current, swap_current, effective):
            problems.append("watchdog preflight memory authorities are incomplete")
        elif swap_current != 0:
            problems.append("watchdog preflight swap is nonzero")
        else:
            assert limit is not None and host_available is not None
            expected_effective = min(limit, host_available, 14 * 1024**3)
            if effective != expected_effective:
                problems.append("watchdog effective memory authority is incorrect")
            if warning_threshold != int(expected_effective * (11.5 / 14.0)):
                problems.append("watchdog warning threshold is incorrectly scaled")
            if termination_threshold != int(expected_effective * (13.0 / 14.0)):
                problems.append("watchdog termination threshold is incorrectly scaled")
    sampling = record.get("sampling")
    if not isinstance(sampling, Mapping):
        problems.append("watchdog sampling evidence is missing")
    else:
        if _integer_or_none(sampling.get("sample_count")) in (None, 0, 1):
            problems.append("watchdog has fewer than two samples")
        for name in (
            "worker_tree_rss_peak_bytes",
            "cgroup_memory_current_peak_bytes",
            "observed_memory_peak_bytes",
            "cgroup_memory_limit_bytes",
            "host_available_memory_min_bytes",
            "swap_current_initial_bytes",
            "swap_current_final_bytes",
            "swap_current_peak_bytes",
            "swap_current_delta_bytes",
            "effective_memory_bytes",
            "warning_threshold_bytes",
            "termination_threshold_bytes",
            "nonzero_swap_sample_count",
            "authority_unreadable_sample_count",
        ):
            if _integer_or_none(sampling.get(name)) is None:
                problems.append(f"watchdog sampling field {name} is missing")
        observed = _integer_or_none(sampling.get("observed_memory_peak_bytes"))
        termination_threshold = _integer_or_none(
            sampling.get("termination_threshold_bytes")
        )
        if (
            observed is not None
            and termination_threshold is not None
            and observed >= termination_threshold
        ):
            problems.append("watchdog observed memory reached termination threshold")
        for name in (
            "swap_current_initial_bytes",
            "swap_current_final_bytes",
            "swap_current_peak_bytes",
            "swap_current_delta_bytes",
            "nonzero_swap_sample_count",
            "authority_unreadable_sample_count",
        ):
            if _integer_or_none(sampling.get(name)) != 0:
                problems.append(f"watchdog requires zero {name}")
        if sampling.get("cgroup_memory_limit_state") != "finite":
            problems.append("watchdog sampled container limit was not finite")
        if sampling.get("raw_output_ignored_by_git") is not True:
            problems.append("watchdog raw sample output is not git-ignored")
        if sampling.get("summary_output_ignored_by_git") is not True:
            problems.append("watchdog summary output is not git-ignored")
    control = record.get("control")
    if not isinstance(control, Mapping):
        problems.append("watchdog control evidence is missing")
    else:
        timeout = _finite_or_none(control.get("wall_timeout_seconds"))
        if timeout is None or timeout <= 0.0:
            problems.append("watchdog wall timeout is missing")
        if control.get("wall_timeout_triggered") is not False:
            problems.append("watchdog wall timeout triggered")
        if control.get("controlled_termination") is not False:
            problems.append("watchdog controlled termination triggered")
        if control.get("termination_trigger") is not None:
            problems.append("watchdog has a termination trigger")
        if isinstance(sampling, Mapping):
            observed = _integer_or_none(sampling.get("observed_memory_peak_bytes"))
            warning_threshold = _integer_or_none(
                sampling.get("warning_threshold_bytes")
            )
            if (
                observed is not None
                and warning_threshold is not None
                and observed >= warning_threshold
                and control.get("warning_triggered") is not True
            ):
                problems.append("watchdog failed to record a crossed warning threshold")
    qualification = record.get("qualification")
    if (
        not isinstance(qualification, Mapping)
        or qualification.get("memory_summary_qualified") is not True
    ):
        problems.append("watchdog memory qualification is not true")
    expected_status = "passed" if not problems else "failed"
    if record.get("status") != expected_status:
        problems.append("watchdog status is inconsistent with its evidence")
    return problems


def _all_pde_rows(shards: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        item
        for shard in shards
        for item in shard.get("pde_results", [])
        if isinstance(item, Mapping)
    ]


def _low_order_fixture_b_sampling_diagnostic(
    coarse: Mapping[str, Any],
    fine: Mapping[str, Any],
    *,
    relative_tolerance: float,
    absolute_tolerance: float,
) -> dict[str, Any] | None:
    """Explain the narrow native-VTU H-Linf sampling artifact, if present.

    This does not waive a general low-order regression.  It applies only to the
    observed p1 case when the oracle provenance is exactly the native-VTU
    mesh-native point set grows, H is the sole native field component that
    regresses, and every mesh-independent Fresnel/power observable is
    non-regressing.  The raw H result remains a failed diagnostic row.
    """

    if (
        coarse.get("fixture") != "fixture_b_flat_air_si"
        or fine.get("fixture") != "fixture_b_flat_air_si"
        or int(coarse.get("degree", 0)) != 1
        or coarse.get("degree") != fine.get("degree")
    ):
        return None

    for row in (coarse, fine):
        if (
            _nested_value(row, ("artifact_validation", "method"))
            != NATIVE_VTU_ORACLE_METHOD
            or _nested_value(
                row,
                ("artifact_validation", "field_errors", "reduction"),
            )
            != NATIVE_VTU_ORACLE_REDUCTION
            or _nested_value(
                row,
                (
                    "artifact_validation",
                    "field_errors",
                    "interface_points_excluded",
                ),
            )
            is not True
        ):
            return None

    field_paths = {
        "E": ("fields", "relative_max_abs_E_error"),
        "H": ("fields", "relative_max_abs_H_error"),
    }
    native_fields: dict[str, dict[str, float]] = {}
    regressed_components: list[str] = []
    for name, path in field_paths.items():
        coarse_value = _nested_number(coarse, path)
        fine_value = _nested_number(fine, path)
        if coarse_value is None or fine_value is None:
            return None
        native_fields[name] = {"h5": coarse_value, "h2p5": fine_value}
        allowed = coarse_value * (1.0 + relative_tolerance) + absolute_tolerance
        if fine_value > allowed:
            regressed_components.append(name)
    if regressed_components != ["H"]:
        return None

    points_path = (
        "artifact_validation",
        "field_errors",
        "global_rank_local_points_compared",
    )
    coarse_points = _nested_number(coarse, points_path)
    fine_points = _nested_number(fine, points_path)
    if (
        coarse_points is None
        or fine_points is None
        or int(fine_points) <= int(coarse_points)
    ):
        return None

    comparable_paths = {
        "reflection_complex_amplitude_absolute_error": (
            "zero_order_complex_amplitudes",
            "reflection_top",
            "absolute_error",
        ),
        "transmission_complex_amplitude_absolute_error": (
            "zero_order_complex_amplitudes",
            "transmission_bottom",
            "absolute_error",
        ),
        "R_reference_absolute_error": ("power", "R_port_minus_R_ref"),
        "T_reference_absolute_error": ("power", "T_port_minus_T_ref"),
        "A_reference_absolute_error": ("power", "A_volume_minus_A_ref"),
    }
    comparable: dict[str, dict[str, float]] = {}
    for name, path in comparable_paths.items():
        coarse_value = _nested_number(coarse, path)
        fine_value = _nested_number(fine, path)
        if coarse_value is None or fine_value is None:
            return None
        coarse_error = abs(coarse_value)
        fine_error = abs(fine_value)
        allowed = coarse_error * (1.0 + relative_tolerance) + absolute_tolerance
        if fine_error > allowed:
            return None
        comparable[name] = {"h5": coarse_error, "h2p5": fine_error}

    for row in (coarse, fine):
        closure = _nested_number(row, ("power", "port_volume_closure_error"))
        if closure is None or abs(closure) > PDE_GATE_LIMITS["fixture_b_port_volume_closure"]:
            return None

    return {
        "reason": "mesh_native_vtu_H_linf_uses_different_point_sets",
        "native_field_errors": native_fields,
        "native_points_compared": {"h5": int(coarse_points), "h2p5": int(fine_points)},
        "mesh_independent_observable_errors": comparable,
    }


def analyze_accuracy_trends(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Classify h and p trends using the physical error scalar.

    A low-order regression remains fail-closed unless the evidence proves the
    narrow Fixture-B native-VTU H-Linf sampling artifact.  High-order p3/p4
    trends are always fail-closed.
    """

    problems: list[str] = []
    warnings: list[str] = []
    negative: list[dict[str, Any]] = []
    h_rows: list[dict[str, Any]] = []
    p_rows: list[dict[str, Any]] = []
    h_groups: dict[tuple[Any, ...], dict[float, Mapping[str, Any]]] = {}
    p_groups: dict[tuple[Any, ...], dict[int, Mapping[str, Any]]] = {}
    for row in rows:
        error = _finite_or_none(row.get("physical_error_scalar"))
        if error is None or error < 0.0 or row.get("physical_qualification_passed") is not True:
            problems.append(
                f"physical qualification/error missing for {row.get('matrix_id')}"
            )
            continue
        h_key = (
            row.get("fixture"),
            row.get("grazing_deg_from_surface"),
            row.get("polarization"),
            row.get("degree"),
            row.get("mpi_size"),
        )
        h_groups.setdefault(h_key, {})[float(row.get("mesh_target_nm"))] = row
        p_key = (
            row.get("fixture"),
            row.get("grazing_deg_from_surface"),
            row.get("polarization"),
            row.get("mesh_target_nm"),
            row.get("mpi_size"),
        )
        p_groups.setdefault(p_key, {})[int(row.get("degree"))] = row

    relative_tolerance = TREND_LIMITS["h_nonincrease_relative_tolerance"]
    absolute_tolerance = TREND_LIMITS["h_nonincrease_absolute_tolerance"]
    for key, variants in sorted(h_groups.items(), key=lambda pair: repr(pair[0])):
        identity = {
            "fixture": key[0],
            "grazing_deg_from_surface": key[1],
            "polarization": key[2],
            "degree": key[3],
            "mpi_size": key[4],
            "gate_scope": "hard_qualification",
        }
        if set(variants) == {5.0} and key[1] in SMOKE_GRAZING_DEG:
            h_rows.append(
                {
                    **identity,
                    "classification": "not_applicable_smoke_h5_only",
                    "passed": True,
                }
            )
            continue
        if set(variants) != {5.0, 2.5}:
            problems.append(f"h-trend coverage is incomplete for {key!r}")
            h_rows.append({**identity, "classification": "missing", "passed": False})
            continue
        coarse = float(variants[5.0]["physical_error_scalar"])
        fine = float(variants[2.5]["physical_error_scalar"])
        allowed = coarse * (1.0 + relative_tolerance) + absolute_tolerance
        passed = fine <= allowed
        diagnostic = None
        if not passed:
            diagnostic = _low_order_fixture_b_sampling_diagnostic(
                variants[5.0],
                variants[2.5],
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
            )
        h_item = {
            **identity,
            "h5_error": coarse,
            "h2p5_error": fine,
            "allowed_h2p5_error": allowed,
            "classification": (
                "nonincreasing_with_tolerance"
                if passed
                else (
                    "negative_diagnostic_mesh_native_H_linf_sampling_regression"
                    if diagnostic is not None
                    else "negative_h_refinement_regression"
                )
            ),
            "passed": passed,
        }
        if diagnostic is not None:
            h_item["gate_scope"] = "diagnostic_mesh_native_vtu_linf"
            h_item["diagnostic_evidence"] = diagnostic
        h_rows.append(h_item)
        if not passed:
            message = f"h5->h2.5 physical error regressed for {key!r}"
            if diagnostic is not None:
                negative.append(dict(h_item))
                warnings.append(f"{message}; native-VTU H-Linf sampling diagnostic only")
            else:
                problems.append(message)

    p_tolerance = TREND_LIMITS["p_nonregression_relative_tolerance"]
    minimum_benefit = TREND_LIMITS["p4_benefit_minimum_relative"]
    for key, variants in sorted(p_groups.items(), key=lambda pair: repr(pair[0])):
        identity = {
            "fixture": key[0],
            "grazing_deg_from_surface": key[1],
            "polarization": key[2],
            "mesh_target_nm": key[3],
            "mpi_size": key[4],
        }
        if set(variants) != set(DEGREES):
            problems.append(f"p-trend coverage is incomplete for {key!r}")
            p_rows.append({**identity, "classification": "missing", "passed": False})
            continue
        errors = {
            degree: float(variants[degree]["physical_error_scalar"])
            for degree in DEGREES
        }
        p3_vs_p2_improvement = (errors[2] - errors[3]) / max(
            errors[2], absolute_tolerance
        )
        p4_vs_p3_improvement = (errors[3] - errors[4]) / max(
            errors[3], absolute_tolerance
        )
        p3_nonregression_passed = (
            errors[3] <= errors[2] * (1.0 + p_tolerance) + absolute_tolerance
        )
        overall_passed = p3_nonregression_passed and (
            errors[4] <= errors[1] * (1.0 + p_tolerance) + absolute_tolerance
        )
        p3_classification = (
            "nonregressing_with_tolerance"
            if p3_nonregression_passed
            else "negative_p3_regression"
        )
        if not p3_nonregression_passed:
            problems.append(f"p3 physical error regressed by more than 5% for {key!r}")
        if errors[4] > errors[3] * (1.0 + p_tolerance) + absolute_tolerance:
            p4_classification = "negative_p4_regression"
            overall_passed = False
            problems.append(f"p4 physical error regressed by more than 5% for {key!r}")
        elif p4_vs_p3_improvement < minimum_benefit:
            p4_classification = "negative_no_clear_p4_benefit"
            item = {
                **identity,
                "classification": p4_classification,
                "p4_vs_p3_relative_improvement": p4_vs_p3_improvement,
            }
            negative.append(item)
            warnings.append(f"no clear p4 benefit for {key!r}")
        else:
            p4_classification = "positive_p4_benefit"
        classification = (
            "negative_p3_regression"
            if not p3_nonregression_passed
            else p4_classification
        )
        p_rows.append(
            {
                **identity,
                "errors_by_degree": {f"p{degree}": errors[degree] for degree in DEGREES},
                "p3_vs_p2_relative_improvement": p3_vs_p2_improvement,
                "p3_nonregression_passed": p3_nonregression_passed,
                "p3_classification": p3_classification,
                "p4_vs_p3_relative_improvement": p4_vs_p3_improvement,
                "p4_classification": p4_classification,
                "classification": classification,
                "passed": overall_passed,
            }
        )
    return (
        {
            "limits": {
                "h_nonincrease_relative_tolerance": relative_tolerance,
                "h_nonincrease_absolute_tolerance": absolute_tolerance,
                "p_nonregression_relative_tolerance": p_tolerance,
                "p4_benefit_minimum_relative": minimum_benefit,
            },
            "h_refinement": h_rows,
            "p_refinement": p_rows,
            "negative_classifications": negative,
            "warnings": warnings,
        },
        problems,
    )


def analyze_constraint_costs(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """Compare p4 setup fraction and per-constrained-DoF cost against p2."""

    problems: list[str] = []
    warnings: list[str] = []
    comparisons: list[dict[str, Any]] = []
    groups: dict[tuple[Any, ...], dict[int, Mapping[str, Any]]] = {}
    for row in rows:
        key = (
            row.get("fixture"),
            row.get("grazing_deg_from_surface"),
            row.get("polarization"),
            row.get("mesh_target_nm"),
            row.get("mpi_size"),
        )
        groups.setdefault(key, {})[int(row.get("degree"))] = row
    for key, variants in sorted(groups.items(), key=lambda pair: repr(pair[0])):
        if 2 not in variants or 4 not in variants:
            problems.append(f"p2/p4 constraint-cost coverage is incomplete for {key!r}")
            continue
        values: dict[int, tuple[float, float, int]] = {}
        for degree in (2, 4):
            row = variants[degree]
            setup = _nested_number(
                row, ("periodic_constraint", "constraint_setup_outer_seconds")
            )
            elapsed = _nested_number(row, ("resources", "elapsed_seconds"))
            constrained = _nested_number(
                row, ("periodic_constraint", "global_constraint_rows")
            )
            if setup is None or elapsed is None or constrained is None or constrained <= 0.0:
                problems.append(f"constraint-cost evidence is incomplete for p{degree} {key!r}")
                break
            values[degree] = (setup, elapsed, int(constrained))
        if len(values) != 2:
            continue
        p2_setup, _, p2_rows = values[2]
        p4_setup, p4_elapsed, p4_rows = values[4]
        setup_fraction = p4_setup / max(p4_elapsed, 1.0e-30)
        per_dof_ratio = (p4_setup / p4_rows) / max(p2_setup / p2_rows, 1.0e-30)
        setup_warning = setup_fraction > TREND_LIMITS["p4_setup_fraction_warning"]
        cost_warning = per_dof_ratio > TREND_LIMITS[
            "p4_per_constrained_dof_cost_ratio_warning"
        ]
        comparison = {
            "fixture": key[0],
            "grazing_deg_from_surface": key[1],
            "polarization": key[2],
            "mesh_target_nm": key[3],
            "mpi_size": key[4],
            "p2_setup_seconds": p2_setup,
            "p2_constrained_dofs": p2_rows,
            "p4_setup_seconds": p4_setup,
            "p4_elapsed_seconds": p4_elapsed,
            "p4_constrained_dofs": p4_rows,
            "p4_setup_fraction": setup_fraction,
            "p4_per_constrained_dof_cost_ratio_vs_p2": per_dof_ratio,
            "setup_fraction_warning": setup_warning,
            "per_constrained_dof_cost_warning": cost_warning,
        }
        comparisons.append(comparison)
        if setup_warning:
            warnings.append(f"p4 setup exceeds 20% of total time for {key!r}")
        if cost_warning:
            warnings.append(f"p4 per-constrained-DoF setup cost exceeds 5x p2 for {key!r}")
    return (
        {
            "warning_limits": {
                "p4_setup_fraction": TREND_LIMITS["p4_setup_fraction_warning"],
                "p4_per_constrained_dof_cost_ratio_vs_p2": TREND_LIMITS[
                    "p4_per_constrained_dof_cost_ratio_warning"
                ],
            },
            "comparisons": comparisons,
            "warnings": warnings,
            "max_p4_setup_fraction": max(
                (item["p4_setup_fraction"] for item in comparisons), default=None
            ),
            "max_p4_per_constrained_dof_cost_ratio_vs_p2": max(
                (
                    item["p4_per_constrained_dof_cost_ratio_vs_p2"]
                    for item in comparisons
                ),
                default=None,
            ),
        },
        problems,
    )


def aggregate_core_records(
    shards: Sequence[Mapping[str, Any]],
    memory_summaries: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate three clean shards plus their external memory summaries."""

    problems: list[str] = []
    if len(shards) != len(MPI_SIZES):
        problems.append("aggregate requires exactly three shard records")
    by_mpi: dict[int, Mapping[str, Any]] = {}
    source_shas: set[str] = set()
    for shard in shards:
        shard_problems = validate_shard_record(shard)
        identity = shard.get("identity")
        mpi_size = identity.get("mpi_size") if isinstance(identity, Mapping) else None
        if type(mpi_size) is int and mpi_size in MPI_SIZES:
            if mpi_size in by_mpi:
                problems.append(f"duplicate MPI{mpi_size} shard")
            by_mpi[mpi_size] = shard
        else:
            problems.append("aggregate received shard with invalid MPI size")
        if isinstance(identity, Mapping):
            source_sha = identity.get("source_commit_full_sha")
            if isinstance(source_sha, str):
                source_shas.add(source_sha)
        problems.extend(
            f"MPI{mpi_size} shard: {problem}" for problem in shard_problems
        )
    if set(by_mpi) != set(MPI_SIZES):
        problems.append("aggregate coverage must be exactly MPI1/MPI2/MPI4")
    if len(source_shas) != 1:
        problems.append("all shards must use the same clean source SHA")
    source_sha = next(iter(source_shas), None)
    if source_sha is None or _FULL_SHA_RE.fullmatch(source_sha) is None:
        problems.append("aggregate has no valid full source SHA")

    memory_summaries = [] if memory_summaries is None else list(memory_summaries)
    if len(memory_summaries) != len(MPI_SIZES):
        problems.append("aggregate requires exactly three watchdog memory summaries")
    memory_by_mpi: dict[int, Mapping[str, Any]] = {}
    for memory in memory_summaries:
        identity = memory.get("identity")
        mpi_size = identity.get("mpi_size") if isinstance(identity, Mapping) else None
        if type(mpi_size) is int and mpi_size in MPI_SIZES:
            if mpi_size in memory_by_mpi:
                problems.append(f"duplicate MPI{mpi_size} watchdog summary")
            memory_by_mpi[mpi_size] = memory
        else:
            problems.append("aggregate received watchdog with invalid MPI size")
            continue
        problems.extend(
            f"MPI{mpi_size} watchdog: {problem}"
            for problem in validate_watchdog_summary(
                memory,
                expected_mpi_size=mpi_size,
                expected_source_sha=source_sha,
            )
        )
    if set(memory_by_mpi) != set(MPI_SIZES):
        problems.append("watchdog coverage must be exactly MPI1/MPI2/MPI4")

    ordered_shards = [by_mpi[size] for size in MPI_SIZES if size in by_mpi]
    mpi_difference, mpi_problems = compute_mpi_result_difference(ordered_shards)
    problems.extend(mpi_problems)
    pde_rows = _all_pde_rows(ordered_shards)
    accuracy_analysis, accuracy_problems = analyze_accuracy_trends(pde_rows)
    problems.extend(accuracy_problems)
    constraint_cost_analysis, cost_problems = analyze_constraint_costs(pde_rows)
    problems.extend(cost_problems)
    if len(accuracy_analysis["h_refinement"]) != 96:
        problems.append("accuracy h-trend analysis does not cover exactly 96 groups")
    if len(accuracy_analysis["p_refinement"]) != 36:
        problems.append("accuracy p-trend analysis does not cover exactly 36 groups")
    if len(constraint_cost_analysis["comparisons"]) != 36:
        problems.append("constraint-cost analysis does not cover exactly 36 p2/p4 groups")

    observed: dict[str, float | None] = {
        "constraint_round_trip_relative_error": None,
        "bloch_trace_mismatch": None,
        "reduced_full_action_relative_error": None,
        "full_true_residual": None,
        "mpi_result_difference": mpi_difference,
    }
    storage_sparse = True
    storage_gather = False
    storage_dense = False
    coverage: list[dict[str, Any]] = []
    for mpi_size in MPI_SIZES:
        shard = by_mpi.get(mpi_size)
        if shard is None:
            continue
        probes = shard.get("algebra_probes")
        if isinstance(probes, list):
            for probe in probes:
                if not isinstance(probe, Mapping):
                    continue
                degree = probe.get("degree")
                if type(degree) is int and degree in DEGREES:
                    coverage.append(
                        {
                            "degree": degree,
                            "mpi_size": mpi_size,
                            "core_algebra_gates_passed": (
                                probe.get("core_algebra_gates_passed") is True
                            ),
                        }
                    )
                else:
                    problems.append(
                        f"MPI{mpi_size} algebra probe has invalid degree identity"
                    )
                for name in (
                    "constraint_round_trip_relative_error",
                    "bloch_trace_mismatch",
                    "reduced_full_action_relative_error",
                ):
                    value = _finite_or_none(probe.get(name))
                    if value is not None:
                        current = observed[name]
                        observed[name] = value if current is None else max(current, value)
                storage_sparse = storage_sparse and (
                    probe.get("sparse_distributed_constraints") is True
                )
                storage_gather = storage_gather or (
                    probe.get("global_boundary_allgather_used") is not False
                )
                storage_dense = storage_dense or (
                    probe.get("dense_boundary_square_formed") is not False
                )
        results = shard.get("pde_results")
        if isinstance(results, list):
            for item in results:
                if not isinstance(item, Mapping):
                    continue
                residual = _nested_number(item, ("algebra", "full_true_residual"))
                if residual is not None:
                    current = observed["full_true_residual"]
                    observed["full_true_residual"] = (
                        residual if current is None else max(current, residual)
                    )
                trace = _nested_number(
                    item, ("algebra", "bloch_trace_mismatch_max")
                )
                if trace is not None:
                    current = observed["bloch_trace_mismatch"]
                    observed["bloch_trace_mismatch"] = (
                        trace if current is None else max(current, trace)
                    )
                algebra = item.get("algebra")
                if isinstance(algebra, Mapping):
                    storage_sparse = storage_sparse and (
                        algebra.get("sparse_distributed_constraints") is True
                    )
                    storage_gather = storage_gather or (
                        algebra.get("global_boundary_allgather_used") is not False
                    )
                    storage_dense = storage_dense or (
                        algebra.get("dense_boundary_square_formed") is not False
                    )

    gates: list[dict[str, Any]] = []
    gates_passed = True
    for name, limit in CORE_GATE_LIMITS.items():
        value = observed[name]
        passed = value is not None and 0.0 <= value <= limit
        gates_passed = gates_passed and passed
        if not passed:
            problems.append(f"aggregate core gate {name} failed or is missing")
        gates.append(
            {
                "name": name,
                "observed": value,
                "limit": limit,
                "passed": passed,
            }
        )
    expected_coverage = {
        (degree, mpi_size) for degree in DEGREES for mpi_size in MPI_SIZES
    }
    observed_coverage = {
        (item.get("degree"), item.get("mpi_size")) for item in coverage
    }
    if len(coverage) != 12 or observed_coverage != expected_coverage:
        problems.append("aggregate algebra coverage is not exactly p1-p4 x MPI1/2/4")
    if not storage_sparse or storage_gather or storage_dense:
        problems.append("aggregate sparse/no-gather/no-dense storage veto failed")

    p1_rows = [
        item
        for shard in ordered_shards
        for item in shard.get("pde_results", [])
        if isinstance(item, Mapping) and item.get("degree") == 1
    ]
    p2_rows = [
        item
        for shard in ordered_shards
        for item in shard.get("pde_results", [])
        if isinstance(item, Mapping) and item.get("degree") == 2
    ]
    p1_pass = len(p1_rows) == 36 and all(
        item.get("numerical_gates_passed") is True for item in p1_rows
    )
    p2_pass = len(p2_rows) == 36 and all(
        item.get("numerical_gates_passed") is True for item in p2_rows
    )
    if not p1_pass or not p2_pass:
        problems.append("ordinary p1/p2 Floquet regression evidence failed")

    all_passed = not problems and gates_passed
    source_clean = (
        len(source_shas) == 1
        and len(ordered_shards) == 3
        and all(
            isinstance(shard.get("identity"), Mapping)
            and shard["identity"].get("source_clean_and_stable") is True
            for shard in ordered_shards
        )
    )
    pde_run = (
        len(ordered_shards) == 3
        and all(
            isinstance(shard.get("identity"), Mapping)
            and shard["identity"].get("is_pde_run") is True
            for shard in ordered_shards
        )
    )
    payload: dict[str, Any] = {
        "schema_version": CORE_SCHEMA_VERSION,
        "record_type": "high_order_floquet_core_gate_result",
        "case_id": CASE_ID,
        "evidence_id": (
            f"case090-pde-core-{source_sha[:12]}" if source_sha else "case090-pde-core-failed"
        ),
        "identity": {
            "is_pde_run": pde_run,
            "is_solver_pass": all_passed,
            "tracked_source_dirty": not source_clean,
            "source_commit_full_sha": source_sha,
        },
        "all_core_gates_passed": all_passed,
        "gates": gates,
        "coverage": sorted(
            coverage, key=lambda item: (int(item["degree"]), int(item["mpi_size"]))
        ),
        "storage_contract": {
            "sparse_distributed_constraints": storage_sparse,
            "global_boundary_allgather_used": storage_gather,
            "dense_boundary_square_formed": storage_dense,
        },
        "ordinary_regression": {
            "p1_existing_floquet_passed": p1_pass,
            "p2_existing_floquet_passed": p2_pass,
        },
        "accuracy_trend_analysis": accuracy_analysis,
        "constraint_cost_analysis": constraint_cost_analysis,
        "external_memory_watchdog": {
            "summary_schema_version": WATCHDOG_SCHEMA_VERSION,
            "all_three_qualified": (
                set(memory_by_mpi) == set(MPI_SIZES)
                and all(
                    not validate_watchdog_summary(
                        memory_by_mpi[size],
                        expected_mpi_size=size,
                        expected_source_sha=source_sha,
                    )
                    for size in MPI_SIZES
                )
            ),
            "summary_evidence_sha256": {
                f"mpi{size}": memory_by_mpi[size].get("evidence_sha256")
                for size in MPI_SIZES
                if size in memory_by_mpi
            },
            "observed_memory_peak_bytes": {
                f"mpi{size}": memory_by_mpi[size].get("sampling", {}).get(
                    "observed_memory_peak_bytes"
                )
                for size in MPI_SIZES
                if size in memory_by_mpi
                and isinstance(memory_by_mpi[size].get("sampling"), Mapping)
            },
        },
        "pde_evidence": {
            "shard_schema_version": SHARD_SCHEMA_VERSION,
            "shard_evidence_sha256": {
                f"mpi{size}": by_mpi[size].get("evidence_sha256")
                for size in MPI_SIZES
                if size in by_mpi
            },
            "case_count_per_shard": {
                f"mpi{size}": len(by_mpi[size].get("pde_results", []))
                for size in MPI_SIZES
                if size in by_mpi
            },
            "mpi_result_comparison_method": (
                "maximum rank-pair relative difference with scale max(1, abs(values))"
            ),
            "rss_note": (
                "PDE rows preserve max-rank historical RSS and the sum of rank "
                "historical peaks; neither is mislabeled as simultaneous RSS."
            ),
        },
        "failures": problems,
    }
    return attach_evidence_sha256(payload)


def read_json_object(path: Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return payload


def write_json_object(path: Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)


def flatten_failures(records: Iterable[Mapping[str, Any]]) -> list[str]:
    return [
        str(problem)
        for record in records
        for problem in record.get("failures", [])
        if isinstance(record.get("failures"), list)
    ]
