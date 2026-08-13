"""Task39 component-only 0.7 nm feasibility evidence.

This module reads only tracked Task39 inputs and compact records.  It never
constructs a mesh, assembles a matrix, or launches a solver.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
    task039_07nm_launch_error,
    task039_air_side_external_mode_inventory,
)
from src.io.resolved_config import canonical_json_bytes, resolved_config_sha256


ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = Path("input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat")
RECORD_DIR = Path("benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records")
T2_PATH = RECORD_DIR / "task039_t2_a0_preflight_v1.json"
T3_PATH = RECORD_DIR / "task039_t3_full3d_direct_mpi8_v1.json"
T4_PATH = RECORD_DIR / "task039_t4_full3d_iterative_mpi8_negative_v1.json"
T5_PATH = RECORD_DIR / "task039_t5_hybrid_direct_m_convergence_v1.json"
ACCEPTED_13P5_PATH = Path(
    "benchmarks/cases/102_hybrid_iterative_robustness/records/"
    "task037c_mpi8_three_way_qualification_v1.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _gib(value: float) -> float:
    return value / 1024**3


def _source_sha(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def _air_authority(specification: Any) -> dict[str, Any]:
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    inventory = task039_air_side_external_mode_inventory(cfg)
    keys = inventory["keys"]
    modes = inventory["modes"]
    key_tuples = [
        (item["side"], item["m"], item["n"], item["polarization"]) for item in keys
    ]
    if len(key_tuples) != len(set(key_tuples)):
        raise ValueError("0.7 nm air inventory contains duplicate keys")
    spatial = sorted({(item["m"], item["n"]) for item in keys})
    counts = inventory["counts"]
    mode_rayleigh = sum(bool(item["rayleigh_warning"]) for item in modes)
    mode_propagating = sum(bool(item["propagating"]) for item in modes)
    if mode_rayleigh != counts["rayleigh_warning"]:
        raise ValueError("air inventory Rayleigh count is inconsistent")
    return {
        "selection": inventory["selection"],
        "source": inventory["source"],
        "wavelength_nm": inventory["wavelength_nm"],
        "air_n": inventory["air_n"],
        "material_status": inventory["material_status"],
        "substrate_status": inventory["substrate_dependent"],
        "full_pde_allowed": inventory["full_pde_allowed"],
        "full_pde_error": inventory["full_pde_error"],
        "count": len(key_tuples),
        "key_shape": ["side", "m", "n", "polarization"],
        "key_sha256": hashlib.sha256(canonical_json_bytes(keys)).hexdigest(),
        "spatial_count": len(spatial),
        "m_bounds": [spatial[0][0], spatial[-1][0]],
        "n_bounds": [min(n for _, n in spatial), max(n for _, n in spatial)],
        "polarization_counts": counts["polarization_per_side"],
        "propagating_count": mode_propagating,
        "nonpropagating_count": counts["nonpropagating"],
        "rayleigh_warning_count": mode_rayleigh,
        "near_cutoff_status": "not_separately_defined_by_authority",
        "zero_order_retained": any((m, n) == (0, 0) for m, n in spatial),
    }


def _external_estimates(air: dict[str, Any], trace_rows: int) -> dict[str, Any]:
    channels = air["count"]
    w_bytes = trace_rows * channels * 16
    k_bytes = channels * channels * 16
    return {
        "trace_rows": trace_rows,
        "N_air": channels,
        "W_bytes_complex128": w_bytes,
        "W_GiB_complex128": _gib(w_bytes),
        "K_bytes_complex128": k_bytes,
        "K_GiB_complex128": _gib(k_bytes),
        "K_LU_bytes_range_complex128": [k_bytes, 2 * k_bytes],
        "K_LU_GiB_range_complex128": [_gib(k_bytes), _gib(2 * k_bytes)],
        "K_LU_assumption": "dense LU uses one to two dense complex128 K copies; pivot/workspace not measured",
        "O_N3_time_relative_to_604_channels": (channels / 604) ** 3,
        "K_factor_time_seconds": {
            "status": "not_established",
            "reason": "no isolated measured 604-channel K-factor timing baseline; O(N^3) ratio alone cannot determine seconds",
        },
        "classification": "derived_estimate",
    }


def _scenario_b(
    base: dict[str, int], air: dict[str, Any], budget: dict[str, Any]
) -> dict[str, Any]:
    volume_scale = (10.0 / 1.0) ** 3
    surface_scale = (10.0 / 1.0) ** 2
    factor_lower_nnz = int(base["factor_nnz"] * volume_scale)
    factor_upper_nnz = round(base["factor_nnz"] * volume_scale ** (4 / 3))
    matrix_nnz = int(base["matrix_nnz"] * volume_scale)
    factor_bytes = [factor_lower_nnz * 16, factor_upper_nnz * 16]
    full_trace = int(base["global_active_trace_rows"] * volume_scale)
    endcap_trace = int(base["endcap_surface_trace_rows"] * surface_scale)
    endcap_external = _external_estimates(air, endcap_trace)
    endcap_w_plus_k_lu = [
        endcap_external["W_GiB_complex128"] + value
        for value in endcap_external["K_LU_GiB_range_complex128"]
    ]
    return {
        "label": "p6/h1 engineering scaling",
        "status": "derived_estimate_not_accuracy_qualified",
        "measured_fit_points": 1,
        "fit_point": {"h_nm": 10.0, "source": "T3/T2 tracked compact evidence"},
        "assumptions": [
            "volume quantities use h^-3 from the sole h10 point",
            "surface trace quantities use h^-2 from the sole h10 point",
            "same-fill direct-factor lower bound uses h^-3",
            "3D nested-dissection upper envelope uses N^(4/3), hence h^-4",
            "factor bytes are complex128 values-only envelopes; sparse indices, factor metadata, and workspace are excluded",
        ],
        "scale": {"volume_h_minus_3": volume_scale, "surface_h_minus_2": surface_scale},
        "cells": int(base["cells"] * volume_scale),
        "full_fe_dofs": int(base["full_fe_dofs"] * volume_scale),
        "global_active_trace_rows": full_trace,
        "endcap_surface_trace_rows_per_side": endcap_trace,
        "matrix_nnz": matrix_nnz,
        "matrix_nnz_classification": "derived_estimate",
        "factor_nnz_range": [factor_lower_nnz, factor_upper_nnz],
        "factor_bytes_range_complex128": factor_bytes,
        "factor_GiB_range_complex128": [_gib(value) for value in factor_bytes],
        "matrix_free_action_cache": {
            "status": "not_established",
            "reason": "no p6/h1 cache/action carrier; T3 is direct assembly evidence",
        },
        "mpi_process_tree_range": {
            "MPI1": "not_established_no_h1_measurement",
            "MPI8": "not_established_no_h1_measurement",
        },
        "external": {
            "global_trace": _external_estimates(air, full_trace),
            "hybrid_endcap_per_side": endcap_external,
            "hybrid_two_endcap_status": "pending_substrate_material",
            "hybrid_two_endcap_W_status": {
                "authority": "not_established",
                "status": "pending_substrate_material",
                "conditional_equal_air_example_bytes": 2
                * endcap_trace
                * air["count"]
                * 16,
                "conditional_equal_air_example_GiB": _gib(
                    2 * endcap_trace * air["count"] * 16
                ),
                "classification": "conditional_example_not_authority",
            },
            "hybrid_known_air_endcap_W_bytes_lower_bound": endcap_trace
            * air["count"]
            * 16,
            "hybrid_known_air_endcap_if_substrate_equal_air_example_bytes": 2
            * endcap_trace
            * air["count"]
            * 16,
            "two_side_lower_bound_note": "only the known air-side component is an unconditional lower bound; equal-air doubling is conditional",
            "hybrid_known_air_endcap_resident_W_plus_K_LU_GiB_range": endcap_w_plus_k_lu,
            "hybrid_known_air_endcap_effective_hard_stop_gib": budget[
                "effective_hard_stop_gib"
            ],
            "hybrid_known_air_endcap_lower_margin_gib": budget[
                "effective_hard_stop_gib"
            ]
            - endcap_w_plus_k_lu[0],
            "hybrid_known_air_endcap_upper_exceeds_effective_hard_stop": endcap_w_plus_k_lu[
                1
            ]
            > budget["effective_hard_stop_gib"],
            "hybrid_two_endcap_conservative_upper_below_hard_stop": False,
        },
        "budget": {
            "physical_memory_gib": 256.0,
            "effective_hard_stop_gib": budget["effective_hard_stop_gib"],
            "factor_upper_gib": _gib(factor_bytes[1]),
            "factor_lower_exceeds_256_gib": _gib(factor_bytes[0]) > 256.0,
            "global_W_exceeds_256_gib": _gib(full_trace * air["count"] * 16) > 256.0,
            "global_W_exceeds_effective_hard_stop": _gib(full_trace * air["count"] * 16)
            > budget["effective_hard_stop_gib"],
        },
    }


def _internal_models(t5: dict[str, Any]) -> dict[str, Any]:
    m480 = t5["runs"]["M480"]["capacity_and_stages"]
    basis_anchor = m480["basis_bytes"]
    coupling_anchor = m480["coupling_bytes"]["value"]
    lambda_ratio = 13.5 / 0.7
    surface_scale = 100

    def model_row(seed_m: int, growth: float, seed_label: str) -> dict[str, Any]:
        m_est = math.ceil(seed_m * growth)
        modal_unknowns = 2 * m_est
        schur_bytes = modal_unknowns**2 * 16
        return {
            "seed_M": seed_m,
            "seed_label": seed_label,
            "M_estimate": m_est,
            "two_M_modal_unknowns": modal_unknowns,
            "anchor_basis_bytes_M480_h10": basis_anchor,
            "anchor_coupling_bytes_M480_h10": coupling_anchor,
            "h1_surface_scale_h_minus_2": surface_scale,
            "basis_bytes_estimate": math.ceil(
                basis_anchor * (m_est / 480) * surface_scale
            ),
            "coupling_bytes_estimate": math.ceil(
                coupling_anchor * (m_est / 480) * surface_scale
            ),
            "scaling_assumption": "T5 M480/h10 measured per-M bytes * (M_est/480) * (10/1)^2; h1 engineering estimate",
            "dense_modal_schur_bytes_estimate": schur_bytes,
            "dense_modal_schur_LU_bytes_estimate": 2 * schur_bytes,
            "O_M3_factor_time_relative_to_seed": (m_est / seed_m) ** 3,
            "classification": "conservative_model_not_measured",
        }

    accepted_models = {}
    lower_bound_models = {}
    for name, power in (
        ("M_proportional_to_1_over_lambda", 1),
        ("M_proportional_to_1_over_lambda_squared", 2),
    ):
        accepted_models[name] = model_row(
            120, (13.5 / 0.7) ** power, "accepted_13p5_M120"
        )
        lower_bound_models[name] = model_row(
            960, (5.0 / 0.7) ** power, "failed_5nm_M960_lower_bound_only"
        )
    return {
        "accepted_13p5_requested_M": 120,
        "accepted_13p5_source": _relative(ACCEPTED_13P5_PATH, ROOT),
        "five_nm_M_robust_h10": "not_established",
        "M960_status": "failed_before_solution_formation_lower_bound_only",
        "M960_two_M_lower_bound": 1920,
        "M480_measured_anchor": {
            "basis_bytes": basis_anchor,
            "coupling_bytes": coupling_anchor,
            "modal_schur_dimensions": m480["modal_schur_dimensions"],
            "modal_schur_storage": m480["modal_schur_storage"],
        },
        "wavelength_ratio_13p5_to_0p7": lambda_ratio,
        "wavelength_ratio_5_to_0p7": 5.0 / 0.7,
        "h1_surface_scale_h_minus_2": surface_scale,
        "accepted_13p5_M120_models": accepted_models,
        "failed_5nm_M960_lower_bound_models": lower_bound_models,
        "modal_schur_condition_and_LU": {
            "status": "not_established",
            "reason": "5 nm augmented direct carriers do not materialize a modal Schur or LU; values above are conditional dense estimates",
        },
    }


def _render_markdown(record: dict[str, Any]) -> str:
    air = record["air_side_inventory"]
    b = record["fe_scenarios"]["B_p6_h1"]
    ext = b["external"]["global_trace"]
    endcap_ext = b["external"]["hybrid_endcap_per_side"]
    endcap_resident = b["external"][
        "hybrid_known_air_endcap_resident_W_plus_K_LU_GiB_range"
    ]
    two_side = b["external"]["hybrid_two_endcap_W_status"]
    k_factor_time = endcap_ext["K_factor_time_seconds"]
    hard_stop = record["resource_budget"]["effective_hard_stop_gib"]
    internal = record["internal_modal_models"]
    accepted_models = internal["accepted_13p5_M120_models"]
    lower_bound_models = internal["failed_5nm_M960_lower_bound_models"]
    return f"""# Task39 0.7 nm 组件级可行性审计

本页只做组件容量和架构审计，不创建网格、不组装矩阵，也不启动完整 0.7 nm PDE。`static condensation`（静态凝聚）先消去单元内部未知量，减少全局系统；它能降低主系统规模，但不能替代材料输入或外部通道存储。`W` 是外部 DtN 通道到有限元迹空间的耦合矩阵，`K` 是通道之间的稠密矩阵；`PSS/USS` 在本审计中没有被伪造为 0.7 nm 实测值。

## 身份与空气侧唯一可运行组件

| 项目 | 结果 |
|---|---|
| 5 nm 输入 | `{record["source"]["input"]["path"]}` |
| 5 nm physical SHA | `{record["source"]["input"]["physical_model_sha256"]}` |
| 0.7 nm 材料 | `0P7NM_MATERIAL_INPUT_INCOMPLETE` |
| 空气侧通道 | `{air["count"]}`；空间 `(m,n)` `{air["spatial_count"]}`；S/P `{air["polarization_counts"]}` |
| key SHA | `{air["key_sha256"]}` |
| Rayleigh warning / near-cutoff / nonpropagating | `{air["rayleigh_warning_count"]} / {air["near_cutoff_status"]} / {air["nonpropagating_count"]}` |
| 完整 PDE launch | 禁止；`{air["full_pde_error"]}` |

空气侧枚举实际复用了 `task039_air_side_external_mode_inventory`；substrate 侧没有被复制为空气，保持 pending。

## FE 场景

```math
h_{{0.7,A}} = h_{{5,\\mathrm{{qualified}}}}\\,\\frac{{0.7}}{{5.0}}.
```

场景 A 为 `not_instantiated/insufficient_fit_points`：T7/T8 未运行，当前没有 5 nm accuracy-qualified 的 h 点，不能用 h10 冒充拟合点。场景 B 只有一个 h10 测点，下面是工程外推，不是收敛结论。

| p6/h1 派生量 | 数值/状态 |
|---|---:|
| cells / full FE DoF | {b["cells"]} / {b["full_fe_dofs"]} |
| global active trace | {b["global_active_trace_rows"]}（h^-3） |
| matrix NNZ | {b["matrix_nnz"]}（derived） |
| factor NNZ range | {b["factor_nnz_range"][0]} – {b["factor_nnz_range"][1]} |
| factor values-only bytes range | {b["factor_GiB_range_complex128"][0]:.2f} – {b["factor_GiB_range_complex128"][1]:.2f} GiB |
| MPI1 / MPI8 process-tree | not_established / not_established |
| matrix-free cache/action | not_established |

```math
N_{{FE}}\\propto h^{{-3}},\\qquad n_{{\\Gamma,\\mathrm{{endcap}}}}\\propto h^{{-2}},\\qquad N_{{factor,upper}}\\propto N_{{FE}}^{{4/3}}.
```

## External DtN/Woodbury容量

| 组件 | trace rows | 单 air-side W | K | K-LU |
|---|---:|---:|---:|---:|
| Full3D/global hypothetical | {ext["trace_rows"]} | {ext["W_GiB_complex128"]:.2f} GiB | {ext["K_GiB_complex128"]:.2f} GiB | {ext["K_LU_GiB_range_complex128"][0]:.2f}–{ext["K_LU_GiB_range_complex128"][1]:.2f} GiB |
| Hybrid per-air-side endcap | {endcap_ext["trace_rows"]} | {endcap_ext["W_GiB_complex128"]:.2f} GiB | {endcap_ext["K_GiB_complex128"]:.2f} GiB | {endcap_ext["K_LU_GiB_range_complex128"][0]:.2f}–{endcap_ext["K_LU_GiB_range_complex128"][1]:.2f} GiB |

Hybrid 双端 W 的 authority 为 `{two_side["authority"]}/{two_side["status"]}`。假设 substrate
与 air 相同的 conditional example 为 `{two_side["conditional_equal_air_example_bytes"]}`
bytes（`{two_side["conditional_equal_air_example_GiB"]:.2f}` GiB）；它不是 authority、无条件
lower bound，也不能替代缺失的 substrate material。16030-channel K factor 相对于
604-channel dense K factor 的 O(N^3) engineering ratio 为
`{endcap_ext["O_N3_time_relative_to_604_channels"]:,.0f}x`。K factor 的绝对秒数为
`{k_factor_time["status"]}`，原因是 {k_factor_time["reason"]}。

Full3D/global 的 W 是全局 hypothetical capacity，不是 Hybrid endcap authority。已知 top-air endcap 的 W 是 `{endcap_ext["W_GiB_complex128"]:.2f}` GiB；把已定义的 1–2 份 K-LU 计入 resident component 后，known air-side endcap 的 `{endcap_resident[0]:.3f}–{endcap_resident[1]:.3f}` GiB range 与 effective hard stop `{hard_stop:.3f}` GiB 比较：lower 仅余 `{b["external"]["hybrid_known_air_endcap_lower_margin_gib"]:.3f}` GiB，upper 已超限。完整 two-endcap status 仍为 `pending_substrate_material`；由于 substrate、indices、pivot、workspace 和其他 solver 对象尚未计入，不能给出低于 hard stop 的保守上界，external redesign 分类成立。K-LU 是 complex128 value-only 组件估计，不含 indices、pivot 或 workspace。

Full3D/global 的 W 超过 256 GiB 仅作为说明；Hybrid external redesign 的判定来自上述 endcap `W + K-LU` resident range，而不是把 global W 冒充 Hybrid 组件。这些仍是组件推导，不是完整 PDE 实测。

## Internal modal / Schur容量

13.5 nm accepted evidence 使用 M120；5 nm 的 `M_robust_h10` 未建立，M960 只是在 canonical trace 失败前得到的未通过下界，不能当作 0.7 nm 预测。以 13.5 nm M120 为起点的两种保守 envelope 如下：

| 锚点/模型 | M estimate | 2M | basis GiB | coupling GiB | dense Schur | dense LU | O(M^3) relative to seed |
|---|---:|---:|---:|---:|---:|---:|---:|
| 13.5 M120 / 1/lambda | {accepted_models["M_proportional_to_1_over_lambda"]["M_estimate"]} | {accepted_models["M_proportional_to_1_over_lambda"]["two_M_modal_unknowns"]} | {accepted_models["M_proportional_to_1_over_lambda"]["basis_bytes_estimate"] / 1024**3:.2f} | {accepted_models["M_proportional_to_1_over_lambda"]["coupling_bytes_estimate"] / 1024**3:.2f} | {accepted_models["M_proportional_to_1_over_lambda"]["dense_modal_schur_bytes_estimate"] / 1024**3:.2f} GiB | {accepted_models["M_proportional_to_1_over_lambda"]["dense_modal_schur_LU_bytes_estimate"] / 1024**3:.2f} GiB | {accepted_models["M_proportional_to_1_over_lambda"]["O_M3_factor_time_relative_to_seed"]:.0f}x |
| 13.5 M120 / 1/lambda^2 | {accepted_models["M_proportional_to_1_over_lambda_squared"]["M_estimate"]} | {accepted_models["M_proportional_to_1_over_lambda_squared"]["two_M_modal_unknowns"]} | {accepted_models["M_proportional_to_1_over_lambda_squared"]["basis_bytes_estimate"] / 1024**3:.2f} | {accepted_models["M_proportional_to_1_over_lambda_squared"]["coupling_bytes_estimate"] / 1024**3:.2f} | {accepted_models["M_proportional_to_1_over_lambda_squared"]["dense_modal_schur_bytes_estimate"] / 1024**3:.2f} GiB | {accepted_models["M_proportional_to_1_over_lambda_squared"]["dense_modal_schur_LU_bytes_estimate"] / 1024**3:.2f} GiB | {accepted_models["M_proportional_to_1_over_lambda_squared"]["O_M3_factor_time_relative_to_seed"]:.0f}x |
| 5 M960 lower bound / 1/lambda | {lower_bound_models["M_proportional_to_1_over_lambda"]["M_estimate"]} | {lower_bound_models["M_proportional_to_1_over_lambda"]["two_M_modal_unknowns"]} | {lower_bound_models["M_proportional_to_1_over_lambda"]["basis_bytes_estimate"] / 1024**3:.2f} | {lower_bound_models["M_proportional_to_1_over_lambda"]["coupling_bytes_estimate"] / 1024**3:.2f} | {lower_bound_models["M_proportional_to_1_over_lambda"]["dense_modal_schur_bytes_estimate"] / 1024**3:.2f} GiB | {lower_bound_models["M_proportional_to_1_over_lambda"]["dense_modal_schur_LU_bytes_estimate"] / 1024**3:.2f} GiB | {lower_bound_models["M_proportional_to_1_over_lambda"]["O_M3_factor_time_relative_to_seed"]:.0f}x |
| 5 M960 lower bound / 1/lambda^2 | {lower_bound_models["M_proportional_to_1_over_lambda_squared"]["M_estimate"]} | {lower_bound_models["M_proportional_to_1_over_lambda_squared"]["two_M_modal_unknowns"]} | {lower_bound_models["M_proportional_to_1_over_lambda_squared"]["basis_bytes_estimate"] / 1024**3:.2f} | {lower_bound_models["M_proportional_to_1_over_lambda_squared"]["coupling_bytes_estimate"] / 1024**3:.2f} | {lower_bound_models["M_proportional_to_1_over_lambda_squared"]["dense_modal_schur_bytes_estimate"] / 1024**3:.2f} GiB | {lower_bound_models["M_proportional_to_1_over_lambda_squared"]["dense_modal_schur_LU_bytes_estimate"] / 1024**3:.2f} GiB | {lower_bound_models["M_proportional_to_1_over_lambda_squared"]["O_M3_factor_time_relative_to_seed"]:.0f}x |

Basis/coupling 列是以 T5 M480/h10 measured per-M bytes 为锚、再乘 M 比例与 h1 surface scale=100 的 engineering estimates，不是 0.7 nm 实测。

这些是 conservative model estimates；当前 augmented direct 路径没有实测 modal Schur condition/LU。quadratic envelope 的 dense LU 已越过 220 GiB，因此按保守模型需要 internal modal Schur redesign。

## 收敛风险与最终边界

13.5 nm accepted iterative M120 的三个 phi case 为 1771–3945 iterations（逐 case 保留在 record）；T4 5 nm Full3D iterative 在 4000 iterations 后 residual 约 0.155，T6 Hybrid iterative 未运行。因此 0.7 nm iteration range 为 `unbounded/not_established`，不能声称已验证。

最终分类：`0P7NM_MATERIAL_INPUT_INCOMPLETE`、`0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET`、`0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN`、`0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN`、`0P7NM_CONVERGENCE_RISK_UNRESOLVED`。`CURRENT_ARCHITECTURE_PLAUSIBLE` 不适用；T6–T8 仍 not_run/blocked，T9 为 component-only，不能升级为 production qualification。

证据只绑定 repo-relative compact records；ignored raw、mesh、matrix、factor 和完整 modal/W/K 数组均未读取或提交。
"""


def build_task039_0p7nm_audit(
    root: str | Path = ROOT, *, source_sha: str | None = None
) -> dict[str, Any]:
    root = Path(root).resolve()
    input_path = root / INPUT_PATH
    t2 = _read(root / T2_PATH)
    t3 = _read(root / T3_PATH)
    t4 = _read(root / T4_PATH)
    t5 = _read(root / T5_PATH)
    accepted = _read(root / ACCEPTED_13P5_PATH)
    specification = load_and_resolve(input_path)
    air = _air_authority(specification)
    t3_mesh = t3["mesh_and_linear_algebra"]
    inherited = t2["inherited_topology"]
    base = {
        "cells": int(t3_mesh["cells"]),
        "full_fe_dofs": int(t3_mesh["full_dofs"]),
        "global_active_trace_rows": int(t3_mesh["active_trace_rows"]),
        "endcap_surface_trace_rows": int(
            inherited["hybrid"]["values"]["bottom"]["active_trace_rows"]
        ),
        "matrix_nnz": int(t3_mesh["condensed_matrix_nnz_used"]),
        "factor_nnz": int(t3_mesh["factor_matrix_nnz"]),
    }
    budget = {
        "physical_memory_gib": 256.0,
        "warning_gib": t2["resource_authority"]["warning_memory_gib"]["value"],
        "configured_hard_stop_gib": t2["resource_authority"][
            "configured_terminate_memory_gib"
        ]["value"],
        "selected_limit_gib": t2["resource_authority"]["selected_finite_limit"]["gib"],
        "effective_hard_stop_gib": t2["resource_authority"]["hard_stop_memory_gib"][
            "value"
        ],
        "swap_preflight_mib": t2["resource_authority"]["process_tree_preflight"][
            "swap_bytes"
        ]
        / 1024**2,
        "classification": "measured_preflight_capacity_plus_derived_threshold",
    }
    b = _scenario_b(base, air, budget)
    launch_config = {
        "dimension": 3,
        "model_id": "task039_0p7nm_component_only",
        "incidence": {"wavelength_nm": 0.7},
    }
    source = {
        "generator": "benchmarks/task039_0p7nm_feasibility.py",
        "source_sha": source_sha or _source_sha(root),
        "input": {
            "path": INPUT_PATH.as_posix(),
            "input_sha256": specification.input_sha256,
            "resolved_config_sha256": resolved_config_sha256(specification),
            "physical_model_sha256": specification.physical_model_sha256,
        },
        "compact_records": {
            path.name: {
                "path": _relative(root / path, root),
                "sha256": _sha256(root / path),
            }
            for path in (T2_PATH, T3_PATH, T4_PATH, T5_PATH)
        },
    }
    accepted_cases = [
        {
            "phi_deg": case["phi_deg"],
            "iterations": case["iterative_M120"]["iterations"],
            "reported_residual": case["iterative_M120"]["residuals"]["reported"],
        }
        for case in accepted["cases"]
    ]
    t4_solver = t4["solver"]
    return {
        "schema_version": "task039.t9.0p7nm.component.v1",
        "record_id": "task039_t9_0p7nm_feasibility_v1",
        "classification": [
            "0P7NM_MATERIAL_INPUT_INCOMPLETE",
            "0P7NM_FE_FACTOR_OR_CACHE_EXCEEDS_256GIB_BUDGET",
            "0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN",
            "0P7NM_REQUIRES_INTERNAL_MODAL_SCHUR_REDESIGN",
            "0P7NM_CONVERGENCE_RISK_UNRESOLVED",
        ],
        "production_validation_allowed": False,
        "full_pde": {
            "allowed": False,
            "launch_error": task039_07nm_launch_error(launch_config),
            "substrate_material": "pending",
        },
        "source": source,
        "air_side_inventory": air,
        "inherited_5nm_measurements": base,
        "resource_budget": budget,
        "fe_scenarios": {
            "A_accuracy_qualified_h_over_lambda": {
                "status": "not_instantiated",
                "reason": "T7/T8 not_run; no 5 nm accuracy-qualified h fit points",
                "formula": "h_0.7_A = h_5_qualified * 0.7 / 5.0",
                "estimates": "insufficient_fit_points",
            },
            "B_p6_h1": b,
        },
        "external_dtn_woodbury": {
            "air_channel_count": air["count"],
            "substrate_side": "pending_0P7NM_MATERIAL_INPUT_INCOMPLETE",
            "scenario_A": "not_instantiated",
            "classification_detail": {
                "full3d_global_W": {
                    "classification": "illustrative_not_hybrid_authority",
                    "basis": "global-trace W is a Full3D/global hypothetical capacity only",
                },
                "hybrid_two_endcap_W": {
                    "classification": "0P7NM_REQUIRES_EXTERNAL_DTN_WOODBURY_REDESIGN",
                    "basis": "known air-side endcap resident upper exceeds the effective hard stop before unknown substrate and other objects",
                    "status": b["external"]["hybrid_two_endcap_status"],
                    "known_air_endcap_resident_W_plus_K_LU_GiB_range": b["external"][
                        "hybrid_known_air_endcap_resident_W_plus_K_LU_GiB_range"
                    ],
                    "effective_hard_stop_gib": budget["effective_hard_stop_gib"],
                    "known_air_endcap_lower_margin_gib": b["external"][
                        "hybrid_known_air_endcap_lower_margin_gib"
                    ],
                    "known_air_endcap_upper_exceeds_effective_hard_stop": b["external"][
                        "hybrid_known_air_endcap_upper_exceeds_effective_hard_stop"
                    ],
                    "conservative_upper_below_hard_stop": b["external"][
                        "hybrid_two_endcap_conservative_upper_below_hard_stop"
                    ],
                },
            },
            "scenario_B": b["external"],
        },
        "internal_modal_models": _internal_models(t5),
        "convergence": {
            "accepted_13p5": {
                "record": _relative(root / ACCEPTED_13P5_PATH, root),
                "iterations_by_phi": accepted_cases,
                "iterations_min": min(item["iterations"] for item in accepted_cases),
                "iterations_max": max(item["iterations"] for item in accepted_cases),
                "status": "accepted_research_only_reference",
            },
            "five_nm_full3d_iterative": {
                "record": _relative(root / T4_PATH, root),
                "iterations": t4_solver["iterations"],
                "reported_residual": t4_solver["reported_residual"],
                "status": "negative_at_max_it",
            },
            "hybrid_iterative_task39": {"status": "not_run"},
            "0p7nm_iteration_range": "unbounded/not_established",
        },
        "evidence_boundary": {
            "read": "tracked dat and compact records only",
            "ignored_raw_read": False,
            "complete_0p7nm_pde": "forbidden",
            "material_guess": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--doc-output", type=Path)
    args = parser.parse_args(argv)
    record = build_task039_0p7nm_audit()
    payload = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    if args.doc_output:
        args.doc_output.parent.mkdir(parents=True, exist_ok=True)
        args.doc_output.write_text(_render_markdown(record), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
