# Stage 4 真实 3D 周期矩形柱使用指南

## 2026-06-23 更新：main.py 配置和 ParaView 场变量

如果从 `src/main.py` 直接运行 Stage 4，推荐先用：

```text
STAGE_CASE_3D = "stage4_block_grating"
MESH_TARGET_SIZE_3D = 50.0
PML_TOP_THICKNESS_3D = 300.0
PML_BOTTOM_THICKNESS_3D = 300.0
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

ParaView 里现在可以直接查看：

```text
E_tot_V_per_m_real / imag / abs   # 总场 E_total
E_b_V_per_m_real / imag / abs     # 分层背景场 E_bg
E_sca_V_per_m_real / imag / abs   # 散射场 E_scat
```

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
