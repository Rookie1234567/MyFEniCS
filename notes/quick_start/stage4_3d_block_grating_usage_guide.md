# Stage 4 真实 3D 周期矩形柱使用指南

## 2026-06-23 更新：当前 Stage 4 只能作为诊断输出

最新检查结果：

```text
stage4_flat_layer_sanity h50/p1/MPI2:
  R/T = 3.373594e-02 / 9.662641e-01
  R+T = 1.000000e+00

stage4_block_grating h50/p1/MPI2:
  R/T = 9.380284e-03 / 1.075087e+00
  R+T = 1.084467e+00
  official_result = False
  case_status = failed_stage4_energy_balance

stage4_2p5d_compare h50/p1:
  serial 3D y-extruded: R+T = 1.117862
  MPI2 3D y-extruded: R+T = 1.220574
```

因此现在不要把真实 grating 的 R/T 当作物理结果。推荐先跑：

```bash
python3 -m src.test.stage4_2p5d_compare --mesh-target-size 50 --nedelec-degree 1
mpiexec -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.test.stage4_2p5d_compare --mesh-target-size 50 --nedelec-degree 1
```

ParaView 中优先看：

```text
E_tot_physical_abs_V_per_m
E_sca_physical_abs_V_per_m
E_b_physical_abs_V_per_m
domain_tag
is_physical_z_region
is_pml_z_region
```

PML 外边界现在对散射场施加零切向 E；注意 Nedelec 强边界控制的是切向分量，不是把 `|E|` 的三个分量全部钉成 0。判断 PML 吸收优先看 `E_sca_pml_abs_V_per_m` 和 summary 里的 `pml_scattered_decay_ratio_top/bottom`。

## 2026-06-23 更新：当前 Stage 4 不再标记为可信结果

当前 Stage 4 block grating 还能跑完并输出 ParaView，但 lossless 情况下 `R+T > 1`，因此程序现在会把它标记为：

```text
official_result = False
diagnostic_only = True
case_status = failed_stage4_energy_balance
```

你现在可以用它看网格、tag、Floquet 约束、PML 衰减和场分量诊断，但不要把 `R/T` 当作真实物理结果。

新增 2.5D 对照命令：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.test.stage4_2p5d_compare \
  --mesh-target-size 50 \
  --nedelec-degree 1
```

这个命令会跑：

```text
reference_2d_tm       # 原 2D TM scattered solver
extruded_3d_stage4    # y 方向完全拉伸的 3D Stage 4
```

当前 h50/p1 诊断显示 3D y-extruded case 与 2D 不一致，并出现明显 `Ey` 分量。这说明下一步应该先修 2.5D 对照，而不是继续相信真实 3D block 的 R/T。

## 2026-06-23 更新：ParaView 中如何避免被 PML 背景场误导

Stage 4 的 `E_b` 是分层 Fresnel 背景场。它会在 PML 中做复坐标延拓，所以 PML 里的 `E_b` 或 `E_tot` 可能很大；这不是“散射场 PML 没有吸收”。看结构附近的真实物理场时，优先用新增的物理区数组：

```text
E_tot_physical_abs_V_per_m
E_sca_physical_abs_V_per_m
E_b_physical_abs_V_per_m
```

看 PML 是否吸收散射场时，优先用：

```text
E_sca_pml_abs_V_per_m
run_summary.json:
  pml_metric_field = E_scat
  pml_scattered_decay_ratio_top
  pml_scattered_decay_ratio_bottom
```

辅助筛选数组：

```text
domain_tag
is_physical_z_region
is_pml_z_region
```

最新 h50/p1/MPI2 验证中，flat-layer sanity 的 calibrated modal R/T 精确回到 Fresnel：

```text
R/T = 3.373594e-02 / 9.662641e-01
R+T = 1.000000e+00
```

默认 block grating 的 calibrated modal R+T 仍为 `1.084467`，说明 h50 粗网格结果目前只能作为 smoke/流程验证，不能当最终定量 benchmark。下一个对齐细化网格是 `h=25 nm`，直接法可能会明显增加内存。

`R_total_from_net_flux/T_total_from_net_flux` 是 diagnostic-only：它用采样点上的 FE-curl 重建 H 做直接 Poynting 通量，flat sanity 中也不如 calibrated modal amplitudes 稳定。正式报告仍看 `R_total/T_total/R_plus_T`。

## 2026-06-23 更新：PML 和 E_exact 的正确查看方式

Stage 4 真实 grating 没有解析精确解，所以现在不再输出：

```text
E_exact_abs_V_per_m
E_error_abs_V_per_m
H_exact_abs_A_per_m
H_error_abs_A_per_m
```

ParaView 里应该按 2D scattered-field 的口径看三套场：

```text
E_tot_V_per_m_*   # 总场 E_total = E_b + E_sca，只建议在物理区解释
E_b_V_per_m_*     # 分层背景场 E_bg，不是精确解
E_sca_V_per_m_*   # 散射场，判断 PML 吸收时优先看它
```

PML 是人工层。Stage 4 的 PML 目标是吸收 `E_sca`，不是让 `E_b` 或 `E_tot` 在 PML 中为零。背景场在 PML 中经过复坐标延拓，可能有明显模值；这不代表 PML 没吸收散射场。

因此检查 PML 时优先看：

```text
run_summary.json:
  pml_metric_field = E_scat
  pml_scattered_decay_ratio_top
  pml_scattered_decay_ratio_bottom

ParaView:
  E_sca_V_per_m_abs
  domain_tag
```

## 2026-06-23 更新：main.py 配置和 ParaView 场变量

如果从 `src/main.py` 直接运行 Stage 4，推荐先用：

```text
STAGE_CASE_3D = "stage4_block_grating"
MESH_TARGET_SIZE_3D = 50.0
PML_TOP_THICKNESS_3D = 250.0
PML_BOTTOM_THICKNESS_3D = 250.0
PERIOD_X_3D = 350.0
PERIOD_Y_3D = 300.0
GRATING_WIDTH_X_3D = 150.0
GRATING_WIDTH_Y_3D = 100.0
GRATING_HEIGHT_3D = 150.0
```

不要直接把 `MESH_TARGET_SIZE_3D` 改成 `30.0`。原因是 Stage 4 当前使用均匀 hexa 网格，并且要求材料界面和 block 边界必须落在网格面上。默认几何下：

```text
h = 50 nm  对齐
h = 25 nm  对齐
h = 30 nm  不对齐，会报错
```

这是故意的保护，不是程序崩溃。它防止 block 边界被 midpoint tag 静默标错。

旧的 `E_V_per_m_*` 仍然保留，含义等同于 `E_tot_V_per_m_*`。

## 2026-06-23 更新：第一版 Stage 4 已接入

这一版先实现一个固定、可验证的真实 3D 周期结构：

```text
上方空气层 + top PML
中心矩形柱 grating
下方 substrate + bottom PML
x/y 双周期 Floquet
未知量为 E_scat，输出 E_total = E_bg + E_scat
```

默认 benchmark 参数：

```text
lambda0 = 633 nm
period_x / period_y = 350 / 300 nm
n_substrate = 1.45
n_grating = 2.0
block size = 150 x 100 x 150 nm
block bottom = z=0
mesh_target_size = 50 nm
nedelec_degree = 1
pml_top/bottom = 250 nm
pml_alpha = 5
```

第一版只支持：

```text
hexahedron mesh
degree=1 N1curl
topological_edges Floquet constraints
rectangular_block_grating
layered Fresnel background
```

如果 block 边界或材料界面没有落在 hexa 网格面上，程序会直接报错，不会用 midpoint 近似悄悄标错材料。

## 推荐运行命令

默认 normal incidence block grating：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

平界面 sanity，不放 grating/source，用来检查 diffraction 后处理能否回到 Fresnel 0 级：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_flat_layer_sanity \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

小角度 oblique smoke：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --incident-theta-deg 10 \
  --incident-phi-deg 90 \
  --polarization-kind s \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

## 输出文件

每次运行会在 `results/3D_stage4_...` 下写出：

```text
run_summary.json
run_log.txt
all_run_summary.json
fields_3d_for_paraview_parallel.pvd
diffraction_orders_3d.json
diffraction_orders_3d.csv
power_metrics_3d.json
```

ParaView 打开：

```text
fields_3d_for_paraview_parallel.pvd
```

重点看：

```text
domain_tag
E_V_per_m_real / E_V_per_m_imag / E_V_per_m_abs
E_tot_V_per_m_real / E_tot_V_per_m_imag / E_tot_V_per_m_abs
E_b_V_per_m_real / E_b_V_per_m_imag / E_b_V_per_m_abs
E_sca_V_per_m_real / E_sca_V_per_m_imag / E_sca_V_per_m_abs
H_A_per_m_real / H_A_per_m_imag / H_A_per_m_abs
```

## summary 里优先检查的字段

```text
field_formulation = layered_scattered
background_added_to_solution = true
rhs_source_region = physical_grating
rhs_source_tag_volumes.grating
rhs_source_norm
E_bg_norm / E_sca_norm / E_total_norm
floquet_num_constraints
floquet_estimated_constraint_memory_mb
R_total / T_total / R_plus_T / A_balance
diffraction_top_fit_residual
diffraction_bottom_fit_residual
diffraction_top_fe_response_condition
diffraction_bottom_fe_response_condition
```

当前第一版 h50/p1 是 smoke benchmark，不是最终高精度结果。`stage4_flat_layer_sanity` 已经回到 Fresnel 解析 R/T；`stage4_block_grating` 的 `R+T` 仍有约 8% 粗网格/边界误差，需要后续继续做 PML、网格和 modal port 收敛。
