# 2026-06-29 更新：3D 求解器按案例拆分前 baseline 冻结

本文件记录重构前旧入口 `src.runners.run_3d_airbox` 的小规模结果，用来在重构后检查“代码拆分有没有改变已有行为”。这里的数值只用于重构回归，不代表所有历史物理模型都已经可信。特别是 Stage 2C Fresnel 的 `R+T > 1` 是旧模型已知问题，本轮不在重构中顺手修公式。

配套机器可读指标表：

```text
notes/test/3d_refactor_baseline_metrics.json
```

## 冻结命令

下面命令在 Docker complex-mode DOLFINx 环境中运行：

```bash
. dolfinx-complex-mode
python3 -m src.runners.run_3d_airbox --stage-case stage1_airbox --case normal --mesh-target-size 100 --nedelec-degree 1 --visualization-degree 1
python3 -m src.runners.run_3d_airbox --stage-case stage1_airbox --case oblique --mesh-target-size 100 --nedelec-degree 1 --visualization-degree 1
python3 -m src.runners.run_3d_airbox --stage-case floquet_airbox --case oblique --mesh-target-size 100 --nedelec-degree 1 --visualization-degree 1
python3 -m src.runners.run_3d_airbox --stage-case pml_airbox --case oblique --incident-theta-deg 30 --mesh-target-size 100 --nedelec-degree 1 --visualization-degree 1
python3 -m src.runners.run_3d_airbox --stage-case fresnel_interface --case oblique --incident-theta-deg 30 --polarization-kind s --mesh-target-size 100 --nedelec-degree 1 --visualization-degree 1
python3 -m src.runners.run_3d_airbox --stage-case fresnel_interface --case oblique --incident-theta-deg 30 --polarization-kind p --mesh-target-size 100 --nedelec-degree 1 --visualization-degree 1
python3 -m src.runners.run_3d_airbox --stage-case stage4_flat_layer_sanity --case normal --mesh-target-size 10 --nedelec-degree 1 --visualization-degree 1 --stage4-dtn-order-policy zero_order
python3 -m src.runners.run_3d_airbox --stage-case stage4_block_grating --case normal --mesh-target-size 10 --nedelec-degree 1 --visualization-degree 1 --stage4-dtn-order-policy zero_order
```

Stage 4 baseline 使用 `--stage4-dtn-order-policy zero_order`，目的是让重构参照运行时间可控。更完整的多衍射级验证仍以后续独立物理验证为准。

## Baseline 汇总

| case_id | 结果目录 | cells | dofs | 关键指标 |
|---|---:|---:|---:|---|
| `stage1_normal_h100_p1` | `results/3D_stage1_airbox_normal_p1_h100p0_20260629_125123` | 1620 | 2297 | `E_err=7.886976e-01`, `H_err=9.538208e-01` |
| `stage1_oblique_h100_p1` | `results/3D_stage1_airbox_oblique_p1_h100p0_20260629_125127` | 1620 | 2297 | `E_err=5.166082e-01`, `H_err=6.429011e-01` |
| `stage2a_floquet_oblique_h100_p1` | `results/3D_floquet_airbox_oblique_p1_h100p0_20260629_125130` | 270 | 1088 | `E_err=1.167041e-01`, `floquet_x=0` |
| `stage2b_pml_oblique_theta30_h100_p1` | `results/3D_pml_airbox_oblique_p1_h100p0_20260629_125135` | 420 | 1653 | `E_err=1.617638e-01`, `pml_proxy=7.507394e-18` |
| `stage2c_fresnel_s_theta30_h100_p1` | `results/3D_fresnel_interface_oblique_p1_h100p0_20260629_125328` | 420 | 1653 | `R=5.460707e-02`, `T=1.128346e+00`, `R+T=1.182953e+00` |
| `stage2c_fresnel_p_theta30_h100_p1` | `results/3D_fresnel_interface_oblique_p1_h100p0_20260629_125516` | 420 | 1653 | `R=5.667056e-02`, `T=1.158050e+00`, `R+T=1.214720e+00` |
| `stage4a_flat_layer_normal_h10_p1` | `results/3D_stage4_flat_layer_sanity_normal_p1_h10p0_20260629_125537` | 1500 | 5335 | `R=1.000000e+00`, `T=4.559376e-12`, `R+T=1.000000e+00` |
| `stage4b_block_grating_normal_h10_p1` | `results/3D_stage4_block_grating_normal_p1_h10p0_20260629_125545` | 1815 | 6384 | `R=1.000000e+00`, `T=3.087835e-12`, `R+T=1.000000e+00` |

## 重构后对比口径

重构后的新入口为：

```text
src/runners/run_3d_cases.py
```

对比时重点检查：

```text
stage_case
case_status
mesh cells
Nedelec dofs
Floquet constraint counts / mismatch
R_total / T_total / R_plus_T
relative_max_abs_E_error / relative_max_abs_H_error
ParaView 输出文件是否存在
```

耗时、最大内存、PETSc 残差只记录，不作为“重构是否等价”的硬判据。
