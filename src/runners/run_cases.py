from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from mpi4py import MPI

from ..common.config import SimulationConfig, project_root
from ..common.output_paths import unique_run_dir
from ..solvers.solve_port_maxwell import run_port_case
from ..solvers.solve_te_maxwell import run_te_case, run_te_port_case
from ..solvers.solve_vector_maxwell import _json_default, run_case


def _parse_complex_index(text: str) -> complex:
    """Parse refractive indices such as 1.45, 0.999+0.002j, or 1.2-0.1i."""

    try:
        return complex(text.strip().replace("I", "j").replace("i", "j"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid complex refractive index {text!r}; use forms such as 1.45 or 0.999+0.002j."
        ) from exc


def _backend_list(name: str) -> list[str]:
    if MPI.COMM_WORLD.size > 1 and name == "both":
        return ["mpc_official"]
    if MPI.COMM_WORLD.size > 1 and name == "manual":
        raise SystemExit(
            "manual backend is serial-only in v2; use constraint_backend='mpc_official' for MPI runs."
        )
    return ["mpc_official", "manual"] if name == "both" else [name]


def _normalize_method(name: str) -> str:
    aliases = {
        "scattered": "scattered",
        "port": "port_total",
        "port_total": "port_total",
        "both": "all",
        "all": "all",
    }
    try:
        return aliases[name]
    except KeyError as exc:
        raise ValueError(
            "calculation_method must be 'scattered', 'port', or 'all'."
        ) from exc


def _formulation_list(method: str) -> list[str]:
    normalized = _normalize_method(method)
    if normalized == "all":
        return ["scattered", "port_total"]
    return [normalized]


def _port_model_list(name: str) -> list[str]:
    if MPI.COMM_WORLD.size > 1:
        if name == "all":
            return ["robin"]
        if name == "dtn":
            raise SystemExit(
                "DtN Fourier port is serial-only in v2; MPI runs currently support the Robin port."
            )
    if name == "all":
        return ["robin", "dtn"]
    if name in ("robin", "dtn"):
        return [name]
    raise ValueError("port_boundary_model must be 'robin', 'dtn', or 'all'.")


def _backends_for_case(
    requested: str, formulation: str, port_model: str | None
) -> list[str]:
    backends = _backend_list(requested)
    if formulation == "port_total" and port_model == "dtn":
        if requested == "both":
            return ["manual"]
        if requested != "manual":
            raise SystemExit(
                "DtN Fourier port is a nonlocal matrix operator and currently supports manual backend only."
            )
    return backends


def _case_name(parts: list[str]) -> str:
    return "_".join(part for part in parts if part)


def _backend_tag(name: str) -> str:
    return {
        "mpc_official": "mpc",
        "mpc_lowlevel": "mpc",
        "manual": "man",
        "mpc_auto": "auto",
        "both": "both",
    }.get(name, name)


def _background_tag(name: str) -> str:
    return {"layered": "lay", "air": "air"}.get(name, name)


def _method_tag(name: str) -> str:
    return {"scattered": "sc", "port_total": "port", "all": "all"}.get(name, name)


def _polarization_tag(name: str) -> str:
    return str(name).lower()


def _planned_case_count(
    formulations: list[str], constraint_backend: str, port_boundary_model: str
) -> int:
    count = 0
    for formulation in formulations:
        if formulation == "scattered":
            count += len(_backends_for_case(constraint_backend, formulation, None))
            continue
        for port_model in _port_model_list(port_boundary_model):
            count += len(
                _backends_for_case(constraint_backend, formulation, port_model)
            )
    return count


def _base_updates(args) -> dict[str, object]:
    updates: dict[str, object] = {}
    for name in (
        "period_x",
        "air_height",
        "substrate_thickness",
        "grating_width",
        "grating_height",
        "lambda0",
        "n_air",
        "n_substrate",
        "n_grating",
        "pml_top_thickness",
        "pml_bottom_thickness",
        "pml_alpha",
        "mesh_cell_shape",
        "near_field_margin_x",
        "near_field_air_top",
        "near_field_sub_depth",
    ):
        value = getattr(args, name, None)
        if value is not None:
            updates[name] = value
    if args.polarization_type is not None:
        updates["polarization_type"] = args.polarization_type
    if args.nedelec_degree is not None:
        updates["nedelec_degree"] = args.nedelec_degree
    if args.visualization_degree is not None:
        updates["visualization_degree"] = args.visualization_degree
    if args.generate_png_plots is not None:
        updates["generate_png_plots"] = args.generate_png_plots
    if args.mesh_target_size is not None:
        updates["mesh_target_size"] = args.mesh_target_size
    if args.incident_angle_deg is not None:
        updates["incident_angle_deg"] = args.incident_angle_deg
    if args.diffraction_order_count is not None:
        updates["diffraction_order_count"] = args.diffraction_order_count
    if args.power_probe_num_points is not None:
        updates["power_probe_num_points"] = args.power_probe_num_points
    if args.compute_power_metrics is not None:
        updates["compute_power_metrics"] = args.compute_power_metrics
    if args.lock_near_field_template is not None:
        updates["mesh_lock_near_field_template"] = args.lock_near_field_template
    return updates


def _number_tag(prefix: str, value: object) -> str:
    text = str(value).replace("-", "m").replace(".", "p")
    return f"{prefix}{text}"


def _shared_run_dir(results_root, base_name: str, unique_output: bool):
    comm = MPI.COMM_WORLD
    if comm.rank == 0:
        chosen = unique_run_dir(results_root, base_name, enabled=unique_output)
    else:
        chosen = None
    chosen_text = comm.bcast(str(chosen), root=0)
    return Path(chosen_text)


def main(argv: list[str] | None = None):
    defaults = SimulationConfig()
    parser = argparse.ArgumentParser(description="Run 2D vector Maxwell Floquet cases.")
    parser.add_argument(
        "--formulation",
        choices=("scattered", "port", "port_total", "both", "all"),
        default=None,
        help="Override config.calculation_method: scattered, port, or all.",
    )
    parser.add_argument(
        "--constraint-backend",
        choices=("mpc_official", "manual", "mpc_auto", "both"),
        default=None,
        help="Override config.constraint_backend.",
    )
    parser.add_argument(
        "--scattering-background",
        choices=("air", "layered"),
        default=None,
        help="Override config.scattering_background for formulation=scattered.",
    )
    parser.add_argument(
        "--port-boundary-model",
        choices=("robin", "dtn", "all"),
        default=None,
        help="Override config.port_boundary_model for formulation=port_total.",
    )
    parser.add_argument(
        "--polarization-type",
        choices=("TM", "TE"),
        default=None,
        help="Override config.polarization_type: TM uses Ex/Ey Nedelec, TE uses scalar Ez.",
    )
    parser.add_argument(
        "--nedelec-degree", type=int, default=None, help="Nedelec edge element degree."
    )
    parser.add_argument(
        "--visualization-degree",
        type=int,
        default=None,
        help="DG visualization degree.",
    )
    parser.add_argument(
        "--generate-png-plots",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Write quick PNG preview plots. Default is false; ParaView VTU/BP output is always kept.",
    )
    parser.add_argument(
        "--mesh-target-size", type=float, default=None, help="Target mesh size in nm."
    )
    parser.add_argument(
        "--mesh-cell-shape",
        choices=("triangle", "quadrilateral"),
        default=None,
        help="2D structured cell shape: triangle or quadrilateral.",
    )
    parser.add_argument(
        "--period-x", type=float, default=None, help="2D period in x, in nm."
    )
    parser.add_argument(
        "--air-height",
        type=float,
        default=None,
        help="Physical air height above the substrate, in nm.",
    )
    parser.add_argument(
        "--substrate-thickness",
        type=float,
        default=None,
        help="Substrate thickness, in nm.",
    )
    parser.add_argument(
        "--grating-width",
        type=float,
        default=None,
        help="Rectangular grating width, in nm.",
    )
    parser.add_argument(
        "--grating-height",
        type=float,
        default=None,
        help="Rectangular grating height, in nm.",
    )
    parser.add_argument(
        "--lambda0", type=float, default=None, help="Vacuum wavelength, in nm."
    )
    parser.add_argument(
        "--n-air",
        type=_parse_complex_index,
        default=None,
        help="Air refractive index; complex values are accepted.",
    )
    parser.add_argument(
        "--n-substrate",
        type=_parse_complex_index,
        default=None,
        help="Substrate refractive index, e.g. 0.999+0.002j for an absorbing material.",
    )
    parser.add_argument(
        "--n-grating",
        type=_parse_complex_index,
        default=None,
        help="Grating refractive index; complex values are accepted.",
    )
    parser.add_argument(
        "--pml-top-thickness",
        type=float,
        default=None,
        help="Top PML thickness for scattered runs.",
    )
    parser.add_argument(
        "--pml-bottom-thickness",
        type=float,
        default=None,
        help="Bottom PML thickness for scattered runs.",
    )
    parser.add_argument(
        "--pml-alpha",
        type=float,
        default=None,
        help="PML strength parameter for scattered runs.",
    )
    parser.add_argument(
        "--incident-angle-deg",
        type=float,
        default=None,
        help="Incident angle in degrees.",
    )
    parser.add_argument(
        "--diffraction-order-count",
        type=int,
        default=None,
        help="Compute R/T diffraction orders from -N to +N.",
    )
    parser.add_argument(
        "--power-probe-num-points",
        type=int,
        default=None,
        help="Number of points on each horizontal probe line for R/T postprocessing.",
    )
    parser.add_argument(
        "--compute-power-metrics",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable R/T postprocessing.",
    )
    parser.add_argument(
        "--lock-near-field-template",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Insert fixed mesh planes around the grating for thickness scans.",
    )
    parser.add_argument(
        "--near-field-margin-x",
        type=float,
        default=None,
        help="Horizontal margin around the grating used by near-field integrals, in nm.",
    )
    parser.add_argument(
        "--near-field-air-top",
        type=float,
        default=None,
        help="Top y coordinate for the air-near integration box, clipped by air_height.",
    )
    parser.add_argument(
        "--near-field-sub-depth",
        type=float,
        default=None,
        help="Depth below y=0 for the substrate-near integration box, clipped by substrate thickness.",
    )
    parser.add_argument(
        "--port-order-count",
        type=int,
        default=None,
        help="Legacy/search cap metadata for DtN order studies; automatic DtN order selection has its own switch.",
    )
    parser.add_argument(
        "--port-dtn-assembly",
        choices=("explicit", "auxiliary"),
        default=None,
        help="Override config.port_dtn_assembly for Fourier DtN ports.",
    )
    parser.add_argument(
        "--port-use-diffraction-orders",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="False: order 0 only. True: automatically include clearly propagating DtN diffraction orders.",
    )
    parser.add_argument(
        "--port-use-pml",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override config.port_use_pml.",
    )
    parser.add_argument(
        "--unique-output",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override config.unique_output. Use --no-unique-output for old fixed output directories.",
    )
    parser.add_argument(
        "--results-root",
        default=None,
        help=(
            "Output root override. The ordinary default remains <repository>/results; "
            "benchmark scripts use benchmarks/artifacts explicitly."
        ),
    )
    args = parser.parse_args(argv)

    calculation_method = _normalize_method(
        args.formulation or defaults.calculation_method
    )
    constraint_backend = args.constraint_backend or defaults.constraint_backend
    scattering_background = args.scattering_background or defaults.scattering_background
    port_boundary_model = args.port_boundary_model or defaults.port_boundary_model
    port_dtn_order_count = (
        args.port_order_count
        if args.port_order_count is not None
        else defaults.port_dtn_order_count
    )
    port_dtn_assembly = args.port_dtn_assembly or defaults.port_dtn_assembly
    port_use_diffraction_orders = (
        defaults.port_use_diffraction_orders
        if args.port_use_diffraction_orders is None
        else args.port_use_diffraction_orders
    )
    port_use_pml = (
        defaults.port_use_pml if args.port_use_pml is None else args.port_use_pml
    )
    unique_output = (
        defaults.unique_output if args.unique_output is None else args.unique_output
    )
    polarization_type = args.polarization_type or defaults.polarization_type

    if calculation_method == "port_total" and constraint_backend == "mpc_auto":
        raise SystemExit(
            "port_total does not use the dolfinx_mpc automatic helper; use manual, mpc_official, or both."
        )
    if port_dtn_order_count < 0:
        raise SystemExit(
            "port_dtn_order_count / --port-order-count must be non-negative."
        )
    if port_dtn_assembly not in ("explicit", "auxiliary"):
        raise SystemExit("port_dtn_assembly must be 'explicit' or 'auxiliary'.")

    root = project_root()
    results_root = Path(args.results_root) if args.results_root else root / "results"
    if not results_root.is_absolute():
        results_root = root / results_root
    common_updates = _base_updates(args)
    formulations = _formulation_list(calculation_method)
    if port_use_pml and "port_total" in formulations:
        raise SystemExit(
            "port_use_pml=True is disabled for port total-field runs. "
            "The current port weak form integrates only physical cells; PML cells would have unconstrained dofs."
        )

    nedelec_for_name = (
        args.nedelec_degree
        if args.nedelec_degree is not None
        else defaults.nedelec_degree
    )
    mesh_for_name = (
        args.mesh_target_size
        if args.mesh_target_size is not None
        else defaults.mesh_target_size
    )
    angle_for_name = (
        args.incident_angle_deg
        if args.incident_angle_deg is not None
        else defaults.incident_angle_deg
    )
    lambda_for_name = args.lambda0 if args.lambda0 is not None else defaults.lambda0
    cell_shape_for_name = (
        args.mesh_cell_shape
        if args.mesh_cell_shape is not None
        else defaults.mesh_cell_shape
    )

    group_parts = ["2D_grating"]
    group_parts.append(_polarization_tag(polarization_type))
    group_parts.append(_method_tag(calculation_method))
    if "scattered" in formulations:
        group_parts.append(_background_tag(scattering_background))
    if "port_total" in formulations:
        group_parts.append(f"pt{port_boundary_model}")
        if port_boundary_model in ("dtn", "all"):
            group_parts.append("dtnauto" if port_use_diffraction_orders else "dtn0")
            group_parts.append("aux" if port_dtn_assembly == "auxiliary" else "exp")
    group_parts.append(f"p{nedelec_for_name}")
    group_parts.append(_number_tag("h", mesh_for_name))
    group_parts.append("quad" if cell_shape_for_name == "quadrilateral" else "tri")
    group_parts.append(_number_tag("lam", lambda_for_name))
    group_parts.append(_number_tag("t", angle_for_name))
    if constraint_backend != "both":
        group_parts.append(_backend_tag(constraint_backend))
    if MPI.COMM_WORLD.size > 1:
        group_parts.append(f"np{MPI.COMM_WORLD.size}")
    run_root = _shared_run_dir(results_root, _case_name(group_parts), unique_output)
    run_root.mkdir(parents=True, exist_ok=True)
    single_case_output = (
        unique_output
        and _planned_case_count(formulations, constraint_backend, port_boundary_model)
        == 1
    )

    summaries = []
    for formulation in formulations:
        if formulation == "scattered":
            backends = _backends_for_case(constraint_backend, formulation, None)
            for backend in backends:
                case_parts = ["sc", _background_tag(scattering_background)]
                if args.nedelec_degree is not None:
                    case_parts.append(f"p{args.nedelec_degree}")
                cfg = SimulationConfig(
                    **{
                        **common_updates,
                        "case_name": _case_name(case_parts),
                        "calculation_method": "scattered",
                        "constraint_backend": backend,
                        "scattering_background": scattering_background,
                        "polarization_type": polarization_type,
                        "use_pml": True,
                    }
                )
                cfg = replace(cfg, case_name=f"{cfg.case_name}_{_backend_tag(backend)}")
                out_dir = (
                    run_root
                    if single_case_output
                    else run_root / cfg.case_name
                    if unique_output
                    else results_root / cfg.case_name
                )
                if cfg.polarization_type.upper() == "TE":
                    summaries.append(
                        run_te_case(cfg, out_dir, constraint_backend=backend)
                    )
                else:
                    summaries.append(run_case(cfg, out_dir, constraint_backend=backend))
            continue

        for port_model in _port_model_list(port_boundary_model):
            backends = _backends_for_case(constraint_backend, formulation, port_model)
            for backend in backends:
                if backend == "mpc_auto":
                    continue
                case_parts = ["port", port_model]
                if args.nedelec_degree is not None:
                    case_parts.append(f"p{args.nedelec_degree}")
                if port_model == "dtn":
                    case_parts.append(
                        "auto" if port_use_diffraction_orders else "order0"
                    )
                    case_parts.append(
                        "aux" if port_dtn_assembly == "auxiliary" else "explicit"
                    )
                if port_use_pml:
                    case_parts.append("with_pml")
                port_updates = dict(common_updates)
                cfg = SimulationConfig(
                    **{
                        **port_updates,
                        "case_name": _case_name(case_parts),
                        "calculation_method": "port",
                        "constraint_backend": backend,
                        "port_boundary_model": port_model,
                        "port_dtn_order_count": port_dtn_order_count,
                        "port_dtn_assembly": port_dtn_assembly,
                        "port_use_diffraction_orders": port_use_diffraction_orders,
                        "use_pml": port_use_pml,
                        "port_use_pml": port_use_pml,
                        "scattering_background": scattering_background,
                        "polarization_type": polarization_type,
                    }
                )
                cfg = replace(cfg, case_name=f"{cfg.case_name}_{_backend_tag(backend)}")
                out_dir = (
                    run_root
                    if single_case_output
                    else run_root / cfg.case_name
                    if unique_output
                    else results_root / cfg.case_name
                )
                if cfg.polarization_type.upper() == "TE":
                    summaries.append(
                        run_te_port_case(cfg, out_dir, constraint_backend=backend)
                    )
                else:
                    summaries.append(
                        run_port_case(cfg, out_dir, constraint_backend=backend)
                    )

    comparison = None
    if MPI.COMM_WORLD.rank == 0:
        summary_path = (
            run_root / "all_run_summary.json"
            if unique_output
            else results_root / "all_run_summary.json"
        )
        summary_path.write_text(
            json.dumps(summaries, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        comparison = {
            "run_root": str(run_root),
            "num_cases": len(summaries),
            "cases": [item["case_name"] for item in summaries],
            "case_power_metrics": [
                {
                    "case_name": item["case_name"],
                    "R_total": item.get("power_metrics", {}).get("R_total"),
                    "T_total": item.get("power_metrics", {}).get("T_total"),
                    "R_plus_T": item.get("power_metrics", {}).get("R_plus_T"),
                    "A_balance": item.get("power_metrics", {}).get("A_balance"),
                    "A_volume": item.get("power_metrics", {}).get("A_volume"),
                    "energy_residual_1_minus_R_minus_T": item.get(
                        "power_metrics", {}
                    ).get("energy_residual_1_minus_R_minus_T"),
                    "poynting_R_plus_T_from_net_flux": item.get(
                        "power_metrics", {}
                    ).get("poynting_R_plus_T_from_net_flux"),
                    "poynting_energy_residual": item.get("power_metrics", {}).get(
                        "poynting_energy_residual"
                    ),
                    "dtn_port_R_total": item.get("dtn_port_power_metrics", {}).get(
                        "R_total"
                    ),
                    "dtn_port_T_total": item.get("dtn_port_power_metrics", {}).get(
                        "T_total"
                    ),
                    "dtn_port_R_plus_T": item.get("dtn_port_power_metrics", {}).get(
                        "R_plus_T"
                    ),
                    "dtn_auxiliary_R_total": item.get(
                        "dtn_auxiliary_power_metrics", {}
                    ).get("R_total"),
                    "dtn_auxiliary_T_total": item.get(
                        "dtn_auxiliary_power_metrics", {}
                    ).get("T_total"),
                    "dtn_auxiliary_R_plus_T": item.get(
                        "dtn_auxiliary_power_metrics", {}
                    ).get("R_plus_T"),
                    "near_field_integrals": item.get("near_field_integrals"),
                }
                for item in summaries
            ],
            "calculation_method": calculation_method,
            "constraint_backend": constraint_backend,
            "scattering_background": scattering_background,
            "polarization_type": polarization_type,
            "port_boundary_model": port_boundary_model,
            "port_dtn_order_count": port_dtn_order_count,
            "port_dtn_assembly": port_dtn_assembly,
            "port_use_diffraction_orders": port_use_diffraction_orders,
            "note": "每次默认生成新的 2D_grating_* 结果文件夹；单个 case 直接输出在该目录，多 case 才创建短子目录。使用 --no-unique-output 可恢复固定目录写法。",
        }
        groups: dict[str, list[dict[str, object]]] = {}
        for item in summaries:
            cfg_data = item["config"]
            if cfg_data.get("calculation_method") == "port":
                key_parts = [
                    cfg_data.get("polarization_type", ""),
                    "port",
                    cfg_data.get("port_boundary_model", ""),
                ]
                if cfg_data.get("port_boundary_model") == "dtn":
                    key_parts.append(
                        "dtnauto"
                        if cfg_data.get("port_use_diffraction_orders")
                        else "dtn0"
                    )
                    key_parts.append(str(cfg_data.get("port_dtn_assembly", "")))
            else:
                key_parts = [
                    cfg_data.get("polarization_type", ""),
                    "scattered",
                    cfg_data.get("scattering_background", ""),
                ]
            groups.setdefault(_case_name([str(part) for part in key_parts]), []).append(
                item
            )
        comparison["same_physics_backend_checks"] = []
        for group_name, items in groups.items():
            if len(items) != 2:
                continue
            first, second = items
            check = {
                "physics_group": group_name,
                "cases": [first["case_name"], second["case_name"]],
                "max_abs_E_total_scalar_difference": abs(
                    first["max_abs_E_total"] - second["max_abs_E_total"]
                ),
                "floquet_mismatch_total_dof": {
                    first["case_name"]: first["floquet_mismatch_total_dof"],
                    second["case_name"]: second["floquet_mismatch_total_dof"],
                },
            }
            if "max_abs_E_scat" in first and "max_abs_E_scat" in second:
                check["max_abs_E_scat_scalar_difference"] = abs(
                    first["max_abs_E_scat"] - second["max_abs_E_scat"]
                )
            if (
                "max_abs_E_scat_reference" in first
                and "max_abs_E_scat_reference" in second
            ):
                check["max_abs_E_scat_reference_scalar_difference"] = abs(
                    first["max_abs_E_scat_reference"]
                    - second["max_abs_E_scat_reference"]
                )
            first_power = first.get("power_metrics", {})
            second_power = second.get("power_metrics", {})
            if first_power and second_power:
                check["R_total_difference"] = abs(
                    first_power["R_total"] - second_power["R_total"]
                )
                check["T_total_difference"] = abs(
                    first_power["T_total"] - second_power["T_total"]
                )
                check["R_plus_T_difference"] = abs(
                    first_power["R_plus_T"] - second_power["R_plus_T"]
                )
                if (
                    first_power.get("poynting_R_plus_T_from_net_flux") is not None
                    and second_power.get("poynting_R_plus_T_from_net_flux") is not None
                ):
                    check["poynting_R_plus_T_difference"] = abs(
                        first_power["poynting_R_plus_T_from_net_flux"]
                        - second_power["poynting_R_plus_T_from_net_flux"]
                    )
            comparison["same_physics_backend_checks"].append(check)
        comparison_path = (
            run_root / "backend_comparison.json"
            if unique_output
            else results_root / "backend_comparison.json"
        )
        comparison_path.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
    return comparison


if __name__ == "__main__":
    main()
