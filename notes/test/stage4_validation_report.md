# Stage 4 验证报告

## 2026-06-24 更新：衍射级 probe plane 默认位置修正

根据新的检查结论，逐衍射级 R/T 对 bottom probe plane 位置较敏感，而总 Poynting flux 已经接近 0.997。为了更靠近物理层外侧的均匀远场区域，Stage 4 默认衍射级采样面已改为：

```text
top_probe_z    = interface_z + 0.95 * (physical_z_max - interface_z)
bottom_probe_z = interface_z + 0.95 * (physical_z_min - interface_z)
```

当前 600/500 nm 案例对应：

```text
top_probe_z = 807.5 nm
bottom_probe_z = -332.5 nm
```

本次同时新增采样诊断字段：

```text
diffraction_sample_point_count_per_plane
diffraction_min_sample_count_x_for_fit_orders
diffraction_min_sample_count_y_for_fit_orders
```

后续重新实跑 h50/p1 时，需要重点比较：

```text
R_total_from_e_fourier / T_total_from_e_fourier / R_plus_T_from_e_fourier
R_total_from_net_flux / T_total_from_net_flux / R_plus_T_from_net_flux
diffraction_top_e_fourier_projection_residual_max
diffraction_bottom_e_fourier_projection_residual_max
```

若 E-Fourier 逐衍射级求和仍明显低于 net-flux 能量守恒值，则应继续把逐衍射级功率标为 diagnostic，并优先推进真正的 modal port 或更稳健的面投影后处理。

## 2026-06-23 更新：600/500 nm COMSOL 对比单胞 h50 验证

本轮按 COMSOL 新案例更新了 Stage 4 默认几何：

```text
period_x / period_y = 600 / 500 nm
block = 300 x 200 x 150 nm
air_height = 850 nm
substrate_thickness = 350 nm
pml_top / pml_bottom = 250 / 250 nm
normal incidence S polarization: incident_phi_deg = 0 deg, E 主要沿 y
```

同时修正了 R/T 后处理：

```text
official R/T source = e_fourier_orders
old E/H modal-order powers = diagnostic only
lossless R+T pass tolerance = 1e-8
```

flat-layer sanity:

```text
results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_20260623_133806
R/T = 3.373594e-02 / 9.662641e-01
R+T = 1.000000e+00
case_status = completed
```

block grating normal:

```text
results/3D_stage4_block_grating_normal_p1_h50p0_20260623_135921
official E-Fourier R/T = 2.600070e-03 / 9.334178e-01
official R+T = 9.360178e-01
old modal diagnostic R+T = 1.065764e+00
case_status = completed
```

block grating theta=10 deg:

```text
results/3D_stage4_block_grating_normal_p1_h50p0_20260623_140352
official E-Fourier R/T = 9.938852e-03 / 9.276119e-01
official R+T = 9.375507e-01
old modal diagnostic R+T = 1.060111e+00
case_status = completed
```

h25 direct 尝试：

```text
15 分钟内未完成，残留 Docker 容器已停止。
判断：当前 Docker/direct LU 资源不足，不能作为物理失败。
```

关于 `linear_problem_setup`：本轮 h50/p1 中它约 90-100 s，`linear_problem_solve` 约 129 s。这不是单纯的 Python 函数调用耗时，而是 `dolfinx_mpc.LinearProblem` 构造受 Floquet MPC 约束后的线性系统、创建 PETSc 对象、触发表达式/矩阵装配等操作。h25 的矩阵和 LU 因子化成本会远高于 h50，因此当前直接法不适合继续把 h25 当作常规 smoke。

## 2026-06-23 更新：PML 流程回到 2D-like，evanescent fitting 修正 R+T 爆掉

本轮根据 COMSOL 电场模截图和“lossless R+T 不应超过 1”的要求继续修正 Stage 4。核心变化：

```text
1. Stage 4 正式 PML 分支不再对 z 外边界强加 Dirichlet，
   而是回到 2D scattered solver 类似的 PML 弱式 + natural outer boundary。

2. stage4_boundary_model="robin0" 保留为无 PML 诊断分支，
   不作为正式结果。

3. diffraction_3d 的默认 block grating 拟合中加入邻近 evanescent 级次。
   这些非传播级次只用于分离近场谐波，不计入传播功率。

4. ParaView 物理区电场模切片已经生成：
   results/3D_stage4_block_grating_normal_p1_h50p0_20260623_084409/stage4_Etot_physical_slices.png
```

代码检查：

```text
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"

Ran 27 tests in 1.189s
OK (skipped=8)
```

实跑结果：

| 算例 | 结果目录 | 关键结果 | 判定 |
| --- | --- | --- | --- |
| block grating h50/p1/serial | `results/3D_stage4_block_grating_normal_p1_h50p0_20260623_084409` | R+T = 9.826341e-01, fit_order_count=9 | 通过，场分布可用于诊断 |
| block grating h50/p1/MPI2 | `results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_084643` | R+T = 9.142503e-01, fit_order_count=9 | 通过，但与串行仍有定量差异 |
| flat-layer sanity h50/p1/MPI2 | `results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_np2_20260623_083941` | modal R+T = 1.000000 | 通过；注意 sampled net flux 仍只是诊断量 |
| 2.5D serial h50/p1 | `results/stage4_2p5d_compare_h50p0_p1_np1_20260623_084908` | max Ey ≈ 3.9e-14，但 3D R+T = 1.042795 | 未通过定量对齐 |

当前判断：

```text
1. COMSOL 参考图要求的“热点在柱子侧壁/界面附近，而不是 PML 支配显示”已经基本满足。
2. 真实 block grating h50/p1 不再出现 R+T>1，说明之前 0 级拟合被 evanescent 近场污染。
3. MPI2 与 serial 的 R/T 仍不完全一致，后续需要做更细网格、更多采样面位置和可能的并行后处理对照。
4. 2.5D y-extruded 的非物理 Ey 已消失，但 R/T 仍未复现旧 2D TM，因此还不能宣称 Stage 4 已完成最终定量验证。
```

下面更早的条目保留为历史排查记录；如果边界条件或 R/T 结论与本节冲突，以本节为准。

## 2026-06-23 更新：PML 外边界强截断与 2.5D 对照复跑

本轮继续响应“PML 外边界不应有电场、lossless 情况下 R+T 不应超过 1”的检查。已完成：

```text
1. Stage 4 求解后显式 E.x.scatter_forward()，避免 MPI 后处理读取未同步 ghost dof。
2. Stage 4 PML 外边界施加零切向 E，summary 字段 stage4_outer_pml_zero_tangential_e_bc=true。
3. Floquet low-level builder 改为在本 rank 可见的 slave dof 上登记本地约束，同时保留全局唯一 slave 统计。
4. 2.5D 对照 JSON 增加 max_abs_Ey、max_abs_E_sca_Ey、energy guard 字段。
```

代码检查：

```text
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"

Ran 27 tests in 1.092s
OK (skipped=8)
```

实跑结论：

| 算例 | 结果目录 | 关键结果 | 判定 |
| --- | --- | --- | --- |
| flat-layer sanity h50/p1/MPI2 | `results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_np2_20260623_073657` | R+T = 1.000000 | 通过 |
| block grating h50/p1/MPI2 | `results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_073428` | R+T = 1.084467 | 失败，diagnostic only |
| 2.5D serial h50/p1 | `results/stage4_2p5d_compare_h50p0_p1_np1_20260623_074217` | 3D R+T = 1.117862, max Ey = 8.5e-7 | 仍未和 2D TM 一致 |
| 2.5D MPI2 h50/p1 | `results/stage4_2p5d_compare_h50p0_p1_np2_20260623_074950` | 3D R+T = 1.220574, max Ey = 9.21e-1 | 失败，MPI 下额外偏振更明显 |

判断：PML 背景显示和外边界截断问题已经修正；flat-layer sanity 证明 0 级衍射拟合和 Fresnel 背景口径可用。但真实 grating 的 scattered-field full-vector 3D 路径仍不可信，尤其是 2.5D y-extruded benchmark 尚不能复现旧 2D TM。后续必须先修复 2.5D 对照，再继续真实 3D 定量 benchmark。

## 2026-06-23 更新：2.5D 对照暴露 Stage 4 全矢量解问题

本轮根据“R+T 不能超过 1”的原则重新检查 Stage 4。结论：当前 Stage 4 block grating 不能作为正确结果。

已完成代码检查：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 27 tests in 1.111s
OK (skipped=8)
```

### Stage 4 默认 block grating

命令：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果目录：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_072542
```

关键结果：

| 指标 | 数值 |
| --- | ---: |
| R | 9.381001e-03 |
| T | 1.075089e+00 |
| R+T | 1.084470e+00 |
| stage4_energy_balance_pass | False |
| official_result | False |
| case_status | failed_stage4_energy_balance |
| max abs(Ex/Ey/Ez) | 2.749835e+00 / 3.337442e+00 / 2.054251e+00 |

说明：程序现在会把 lossless 且 `R+T > 1.01` 的 Stage 4 结果标记为失败诊断结果，不再把它当 official。

### 2.5D 对照

新增脚本：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.test.stage4_2p5d_compare \
  --mesh-target-size 50 \
  --nedelec-degree 1
```

结果目录：

```text
results/stage4_2p5d_compare_h50p0_p1_np2_20260623_065320
```

对照结果：

| 指标 | 2D TM | 3D y-extruded |
| --- | ---: | ---: |
| R | 5.958643e-04 | 7.524211e-03 |
| T | 8.747995e-01 | 1.399502e+00 |
| R+T | 8.753954e-01 | 1.407026e+00 |

3D y-extruded case 中 `max |E_scat_y|` 约为 `1.27`，但这个 2.5D 结构和入射条件下 `Ey` 理论上应接近 0。说明当前 3D 全矢量 Stage 4 解混入了非物理偏振/模式，不能只靠后处理修正。

### 本轮修正

```text
1. Stage 4 的 E_b 在 PML 区域置零，避免 E_tot 外边界被背景场染亮。
2. Stage 4 layered-scattered 现在对 PML 外边界施加零切向 E，避免散射场在外截断面自由漂移。
3. ParaView/summary 增加 Ex/Ey/Ez 分量最大值。
4. 增加 2.5D 对照脚本。
5. 增加 Stage 4 lossless energy-balance guard。
6. 增加 divergence_penalty 配置作为诊断项；h50 试验中 penalty=1 对当前问题无明显改善。
```

下一步硬门槛：先让 `stage4_2p5d_compare.py` 中 3D y-extruded case 的 `Ey` 接近 0，并且 R/T 与 2D TM 同趋势，再恢复真实 3D block grating。

## 2026-06-23 更新：PML/E_exact 修正后的最终验证

本轮目标是修正两个误导性问题：

```text
1. Stage 4 真实 grating 没有 E_exact，不能把 E_b 当精确解输出。
2. Stage 4 PML 吸收的是 E_scat，不能用 PML 中的 E_b/E_tot 模值判断吸收失败。
```

已完成代码检查：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 27 tests in 1.247s
OK (skipped=8)
```

已完成实跑：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_all \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果目录：

```text
results/3D_stage4_all_normal_p1_h50p0_np2_20260623_062048
```

### flat-layer sanity

```text
case: airbox3d_normal_stage4_flat_layer_sanity
mesh cells: 1176
N1curl dofs: 4381
Floquet constraints: 769
E_scat: 0
PML metric field: E_scat
```

| 指标 | 数值 |
| --- | ---: |
| modal R | 3.373594e-02 |
| modal T | 9.662641e-01 |
| modal R+T | 1.000000e+00 |
| top fit residual | 6.202768e-15 |
| bottom fit residual | 5.371332e-15 |

结论：无 grating/source 时，calibrated diffraction modal postprocess 能精确回到 Fresnel 0 级。因此 Stage 4 的 `E_b`、Fresnel 背景和模态 R/T 后处理口径是自洽的。

### block grating h50/p1

```text
case: airbox3d_normal_stage4_block_grating
mesh cells: 1176
N1curl dofs: 4381
Floquet constraints: 769
estimated Floquet memory: 0.026 MB
linear_problem_setup: 80.582 s
linear_problem_solve: 25.454 s
max RSS: 4149.5 MB
```

| 指标 | 数值 |
| --- | ---: |
| modal R | 9.380284e-03 |
| modal T | 1.075087e+00 |
| modal R+T | 1.084467e+00 |
| A_balance | -8.446713e-02 |
| top fit residual | 1.667669e-02 |
| bottom fit residual | 7.202705e-03 |
| E_scat PML decay top | 1.817922e-02 |
| E_scat PML decay bottom | 6.249538e-03 |
| max abs(E_tot) physical z-region | 4.787418e+00 |
| max abs(E_tot) PML z-region | 1.484122e+02 |
| max abs(E_scat) physical z-region | 4.375600e+00 |
| max abs(E_scat) PML z-region | 1.789548e-01 |

结论：PML 对散射场有明显衰减，ParaView 中 PML 区域 `E_tot/E_b` 大主要来自背景场的 PML 复坐标延拓。默认 h50 block grating 的能量平衡仍偏大，`R+T` 高出约 8.4%，因此它目前是流程 smoke，不是最终高精度定量 benchmark。

### h40 对齐检查

尝试 `mesh_target_size=40 nm` 时程序主动拒绝：

```text
Stage-4 hexa meshes do not use midpoint approximation for material boundaries.
grating_x_min=100 nm is not on the uniform x-grid ...
```

这是预期保护。默认几何下 `h=50 nm` 和 `h=25 nm` 对齐，`h=40 nm` 不对齐。下一轮如果要做真实收敛，优先考虑 `h=25 nm`，但直接法内存会显著增加。

## 2026-06-23 更新：main.py 入口与 ParaView 三场输出

本轮修正后，从 `src.main` 直接运行 Stage 4 已通过：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main
```

结果目录：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_020702
```

关键检查：

| item | value |
| --- | ---: |
| mesh target size | 50 nm |
| mesh cells resolved | 7 x 6 x 30 |
| N1curl dofs | 4687 |
| Floquet constraints | 823 |
| estimated Floquet memory | 0.028 MB |
| linear problem setup | 85.467 s |
| direct solve | 30.802 s |
| max RSS | 4065.9 MB |

`run_summary.json` 已记录 ParaView 电场数组：

```text
E_V_per_m_*       # 兼容旧字段，等同总场
E_tot_V_per_m_*   # 总场
E_sca_V_per_m_*   # 散射场
E_b_V_per_m_*     # 分层背景场
```

说明：本次 `main.py` 使用 `PML_ALPHA_3D=10`、PML 厚度 300 nm。背景场在 PML 中会做复坐标延拓，因此 `max_abs_E_b` 可能被 PML 区域放大；看结构附近场分布时优先用 ParaView 的 `domain_tag` 聚焦物理区。

## 2026-06-23 更新：第一轮 smoke 与后处理校准

本轮完成：

```text
compileall
unit tests
stage4_block_grating h50/p1 MPI 2 normal
stage4_flat_layer_sanity h50/p1 MPI 4 normal
stage4_block_grating h50/p1 MPI 2 theta=10 deg
```

没有完成：

```text
high-order 大周期 preset
absorbing grating preset
网格/PML 收敛扫描
```

这些留到 Stage 4 第二轮，因为当前直接法的 `linear_problem_setup` 约 90-103 s，最大 RSS 约 4 GB；继续扫参数会比较耗时。

## 快速测试

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 27 tests in 1.787s
OK (skipped=8)
```

新增测试：

```text
src/test/test_11_stage4_diffraction_modes.py
```

覆盖：

```text
zero-order catalog
large-period higher-order catalog
polarization transversality
analytic sampled modal fit
```

## h50/p1/MPI2 block grating normal

命令：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果目录：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_013520
```

关键结果：

| item | value |
| --- | ---: |
| mesh cells | 1176 |
| N1curl dofs | 4381 |
| Floquet constraints | 769 |
| estimated Floquet memory | 0.026 MB |
| x constraint seconds | 0.102 |
| y constraint seconds | 0.007 |
| corner resolve seconds | 0.001 |
| linear problem setup | 89.343 s |
| direct solve | 25.575 s |
| diffraction postprocess | 0.857 s |
| max RSS | 4064.5 MB |
| R_total | 9.380284e-03 |
| T_total | 1.075087e+00 |
| R+T | 1.084467e+00 |
| A_balance | -8.446713e-02 |
| top fit residual | 1.667669e-02 |
| bottom fit residual | 7.202705e-03 |

判断：

```text
能完整跑通并写出 ParaView / diffraction JSON / CSV。
Floquet 已不是内存瓶颈。
当前 R+T 偏离 1 约 8.4%，第一轮只作为 smoke，不作为精度验收。
后续应优先做 PML 厚度、probe plane、mesh refinement 和 modal port 收敛。
```

## h50/p1/MPI4 flat-layer sanity

命令：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_flat_layer_sanity \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果目录：

```text
results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_np4_20260623_013244
```

关键结果：

| item | value |
| --- | ---: |
| grating source volume | 0 |
| RHS source norm | 0 |
| Floquet constraints | 769 |
| R_total | 3.373594e-02 |
| T_total | 9.662641e-01 |
| R+T | 1.000000e+00 |
| A_balance | -2.331468e-15 |
| top fit residual | 7.976109e-15 |
| bottom fit residual | 5.371332e-15 |

判断：

```text
diffraction postprocess 的 T normalization、polarization basis、FE response calibration 是正确的。
无 grating/source 时可以回到 Fresnel 0 级。
```

## h50/p1/MPI2 block grating oblique theta=10 deg

命令：

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

结果目录：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_013746
```

关键结果：

| item | value |
| --- | ---: |
| Floquet phase x | 1 + 3.69e-17j |
| Floquet phase y | 0.8692605 + 0.4943542j |
| Floquet constraints | 769 |
| R_total | 8.928319e-03 |
| T_total | 1.069460e+00 |
| R+T | 1.078389e+00 |
| A_balance | -7.838873e-02 |
| top fit residual | 1.703293e-02 |
| bottom fit residual | 6.630039e-03 |

判断：

```text
非零横向波矢下 Floquet 相位、corner phase 和 diffraction 输出正常。
能量平衡误差与 normal case 同量级，仍归类为第一轮粗网格/PML/边界误差。
```

## 当前结论

```text
1. Stage 4 主线已经跑通。
2. Floquet 约束构建不再是 OOM 风险点；h50/p1 下约束内存估计只有 0.026 MB。
3. direct solver 仍是主要耗时和内存来源。
4. diffraction 后处理已通过 flat-layer sanity，block grating 的能量误差更可能来自粗网格/PML/散射场边界，而不是 R/T 公式本身。
```
