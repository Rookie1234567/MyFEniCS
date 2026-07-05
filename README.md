# MyFEniCS：二维/三维频域 Maxwell 有限元验证程序

本仓库用于开发和验证基于 FEniCSx/DOLFINx 的频域波动光学有限元程序，目标问题是微纳周期结构在 EUV 波段下的散射、反射、透射和材料吸收计算。

当前代码仍处于验证和研发阶段。已有结果中，部分路径可以作为数值 sanity 或代码路径验证；真实 3D EUV 周期光栅的最终物理 benchmark 尚未完成。

---

## 0. 当前合并版本状态

当前阶段分支：

```text
codex/20260704-reduced-height-grating-convergence-memory
```

task002/task003/task004/task005 已作为阶段性版本合并到 `master`。task006 在 task005 基础上测试了真实 3D 光栅 70 nm reduced-height domain 的 p=1/p=2 assemble-only、default direct、MUMPS OOC、MPI=1 对照、R/T/A 初步收敛和 70 nm vs 150 nm 对照。task004/task005 合并后的基础能力含义是：

```text
完成 R/T/A 输出重构、A_volume 体吸收、flat-layer 解析参考、small-cell p=1/p=2 收敛、MPI 1/4/8 一致性与全阶段 smoke 回归。
```

本次合并不代表：

```text
真实 100 nm 3D EUV grating 已完成物理收敛 benchmark。
```

task006 的当前结论是：

```text
70 nm reduced-height domain 可以显著降低矩阵规模；
但 h=5 的 70 nm vs 150 nm R/T/A 差异明显，暂不能视为物理等价计算域；
p=1 default direct 可完成到 h=2 nm；
p=2 default direct 可完成到 h=4 nm；
p=2 h=1 nm assemble-only 在约 40 GB AIJ base matrix 后被 signal 9 kill。
```

当前版本边界详见：

```text
notes/reference/current_version_boundaries.md
docs/task004_small_cell_p_convergence_mpi_regression/review_report.md
docs/task005_stage4_real_grating_memory_estimation/outcomes/summary.md
docs/task006_reduced_height_grating_convergence_memory/outcomes/summary.md
```

2026-07-05 补充：task006 已重新整理 summary，加入 memory profiling、tuned MUMPS OOC、assemble-only 与 direct solve 失败原因解释，以及 h=0.5/h=0.25 nm 的 workstation 外推。当前 reduced-height p=2 的 direct/OOC 可完成边界是 h=4 nm；h=3 nm tuned OOC 仍失败。h<=1 nm 应视为 TB 级或更高资源问题，h=0.5/h=0.25 nm 不适合继续用 direct/OOC workstation 路线硬推。

---

## 1. 当前代码已开发的主要功能

### 1.1 二维 EUV 周期光栅

二维主线用于 100 nm 周期 EUV 矩形光栅的 TM 偏振验证。

已具备：

```text
2D H(curl) / Nedelec 有限元
TM 矢量模型：Ex/Ey
周期/Floquet 约束
DtN / periodic port 边界
端口辅助变量 auxiliary 装配
衍射级 R/T 后处理
近场积分区域：grating / air_near / sub_near
三角形与四边形结构化网格对比
mesh convergence / air scan / substrate scan / combined scan 批量 study
```

主要入口：

```text
src/main.py                         # PyCharm 直接运行入口
src/runners/run_cases.py            # 2D CLI 入口
src/studies/run_2d_euv_validation.py
```

重点说明文档：

```text
notes/quick_start/2d_euv_grating_dtn_usage_guide.md
notes/test/2d_euv_validation_report.md
notes/theory/reflection_transmission_metrics.md
```

当前 2D 推荐口径：

```text
formulation = port
port_boundary_model = dtn
port_dtn_assembly = auxiliary
polarization = TM
mesh_cell_shape = triangle
```

---

## 2. 三维 staged Maxwell 验证链条

三维代码按 staged case 开发。统一入口为：

```text
python3 -m src.runners.run_3d_cases --stage-case <stage_case>
```

PyCharm 直接运行时可改：

```text
src/main.py
SIMULATION_DIMENSION = "3d"
ACTIVE_3D_INPUT_GROUP = "stage1_airbox" / "stage2_no_grating" / "stage4_grating"
```

### 2.1 Stage 1：空气盒子传播

stage case：

```text
stage1_airbox
```

用途：验证三维 N1curl Maxwell 最小框架、入射平面波、基础装配和直接求解流程。

主要入口：

```text
src/solvers/solve_maxwell_3d_stage_1_airbox.py
```

### 2.2 Stage 2A：Floquet 空气盒子

stage case：

```text
floquet_airbox
```

用途：验证 x/y 双向 Floquet 周期约束与三维传播场。

主要入口：

```text
src/solvers/solve_maxwell_3d_stage_2a_floquet_airbox.py
```

### 2.3 Stage 2B：PML 空气盒子

stage case：

```text
pml_airbox
```

用途：验证上下 PML 与 Floquet 侧边界组合。

主要入口：

```text
src/solvers/solve_maxwell_3d_stage_2b_pml_airbox.py
```

### 2.4 Stage 2C：Fresnel 平坦界面

stage case：

```text
fresnel_interface
```

用途：验证空气/基底平坦界面的 incident-scattered 求解口径，并与 Fresnel 解析参考对比。

注意：task004 中 Stage 2B/2C 只做了极粗网格 smoke，不代表 PML/Fresnel 精度已经通过。

主要入口：

```text
src/solvers/solve_maxwell_3d_stage_2c_fresnel_interface.py
```

### 2.5 Flat-layer sanity：平坦界面 DtN 端口校准

stage case：

```text
stage4_flat_layer_sanity
```

注意：这个 case 是平坦界面 sanity，不应称为 3D 光栅散射。代码历史文件名中保留了 `stage_4a_flat_layer_sanity`，但本文档中将其定义为 flat-layer sanity，用于校准：

```text
DtN port
A_volume 材料体吸收
flat-layer analytic reference
probe_eh_fourier / net_flux diagnostic
small-cell p=1/p=2 收敛性
MPI 1/4/8 一致性
```

主要入口：

```text
src/solvers/solve_maxwell_3d_stage_4a_flat_layer_sanity.py
src/postprocessing/flat_layer_reference_3d.py
```

当前建议使用 small-cell 配置进行校准：

```text
period_x = period_y = 10 nm
air_height = substrate_thickness = 5 nm
lambda0 = 13.5 nm
n_substrate = 0.999002304859 + 0.00182649365j
nedelec_degree = 2
```

该配置没有横向结构，理论上只有零级传播通道，可避免 100 nm 周期下 auto_propagating 枚举大量无物理激发的端口模态。

当前结论：

```text
p=2 明显优于 p=1；
port + A_volume 主线稳定闭合；
MPI 1/4/8 不改变主线结果。
```

### 2.6 Stage 4：真实 3D 周期矩形柱/光栅散射

stage case：

```text
stage4_block_grating
```

这是当前真实 3D 周期矩形柱/光栅散射路径。

默认结构：

```text
period_x = period_y = 100 nm
air_height = 100 nm
substrate_thickness = 50 nm
grating_width_x = grating_width_y = 50 nm
grating_height = 50 nm
lambda0 = 13.5 nm
n_substrate = Si complex index
n_grating = Si complex index
```

主要入口：

```text
src/solvers/solve_maxwell_3d_stage_4b_block_grating.py
```

当前状态：

```text
p=1: 可运行，受 3D EUV 网格和直接法内存限制明显。
p=2: Stage 4 block grating 路径已开放，但仍以 smoke / sanity 为主。
zero-contrast smoke: task004 已通过，用于确认几何/tag/输出路径不崩溃。
真实 100 nm grating 的 h≈1 nm 物理收敛不适合作为小电脑阶段验收目标。
```

---

## 3. 三维边界条件与求解口径

### 3.1 Floquet 周期边界

x/y 侧边使用 Floquet MPC 约束。

当前支持：

```text
p=1 N1curl: edge dof 显式拓扑配对
p=2 N1curl: edge dof + face-interior trace dof 拓扑/局部 moment fit 约束
p>=3: 暂未开放
```

主要代码：

```text
src/constraints/floquet_3d.py
```

### 3.2 PML

Stage 2B 和历史 Stage 4 PML 诊断路径支持上下 PML。当前 Stage 4 主线不再依赖 PML 给出 R/T，而是优先使用 DtN port。

主要代码：

```text
src/solvers/common_3d_forms.py
src/solvers/solve_maxwell_3d_stage_2b_pml_airbox.py
```

### 3.3 DtN total-field port

Stage 4 主线是 total-field DtN port：

```text
unknown = E_total
top port = incident Floquet fundamental + outgoing reflected orders
bottom port = outgoing transmitted orders
x/y side = Floquet MPC
z top/bottom = Fourier-DtN auxiliary modal unknowns
PML = 不用于 dtn_port 主线
```

功率读取口径：

```text
top outgoing amplitude    = total_projection - incident_projection
bottom outgoing amplitude = total_projection
R/T = outgoing modal power / incident power
```

主要代码：

```text
src/solvers/dtn_port_3d.py
src/common/modes_3d.py
```

---

## 4. 后处理与输出文件

Stage 4 当前正式输出结构包括：

```text
run_summary.json
power_summary.csv
port_power.json
probe_power.json
flux_power.json
volume_absorption.json
flat_layer_reference.json      # flat-layer sanity 时输出
power_consistency.json         # flat-layer sanity 时输出
```

### 4.1 port

`port` 是当前 Stage 4 的 primary 功率口径，来自 DtN auxiliary modal amplitudes。

### 4.2 volume_absorption

`A_volume` 是材料体吸收检查，当前公式为：

```text
P_abs = integral 0.5*k0*Im(epsilon_r)*|E_total|^2 dV
A_volume = P_abs / P_inc
```

它只积分真实材料区域，排除空气和 PML。当前 small-cell flat-layer 中，`A_volume` 与 `A_port` 可以达到机器精度闭合。

主要代码：

```text
src/postprocessing/rta_3d.py
```

### 4.3 probe_eh_fourier

`probe_eh_fourier` 使用 probe plane 上的 E/H Fourier directional fitting 区分 up/down 波。analytic-only 测试已经通过，但 FEM 场下仍受离散采样和 curl 重构误差影响，目前保留为 diagnostic only。

主要代码：

```text
src/postprocessing/diffraction_3d.py
```

### 4.4 net_flux

`net_flux` 是采样 Poynting flux 总能流诊断，不分衍射级。目前同样作为 diagnostic only。

---

## 5. 网格与单元

当前支持：

```text
2D: triangle / quadrilateral
3D Stage 1: tetrahedron 或 auto
3D Floquet/Stage 4: hexahedron 为主
N1curl p=1 / p=2
```

Stage 4 hexa 网格支持：

```text
uniform_strict
boundary_fitted
local_refined
```

其中 `boundary_fitted` 会自动插入光栅边界、界面等材料面，避免 cell 横跨材料跳变；`local_refined` 是几何驱动的局部结构化加密，不是误差估计 AMR。

主要代码：

```text
src/geometry/mesh_builder_3d.py
```

---

## 6. 并行与求解器

当前支持 MPI 运行，例如：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_cases --stage-case stage4_block_grating
```

task004 已验证 small-cell flat-layer 中 MPI 1/4/8 不改变主线结果：

```text
R_port / T_port / A_volume 与串行差异低于 1e-8；
closure 差异低于 1e-10。
```

注意事项：

```text
1. MPI 下 ParaView 输出使用 PVD/VTU，而不是 3D VTX .bp。
2. summary 指标使用 owned-cell 过滤，避免 ghost cell 重复计数。
3. 当前公开 direct solver profile 只保留 default 和 mumps_ooc。
4. MUMPS out-of-core 可用于内存压力诊断，但不能根本消除 3D direct LU fill-in 问题。
```

相关代码：

```text
src/solvers/common_3d_solve.py
src/postprocessing/postprocess_3d.py
src/studies/run_3d_matrix_scale.py
```

---

## 7. 推荐使用方式

### 7.1 PyCharm 直接运行

修改：

```text
src/main.py
```

选择：

```text
SIMULATION_DIMENSION = "2d" 或 "3d"
ACTIVE_2D_INPUT_GROUP = "euv_grating"
ACTIVE_3D_INPUT_GROUP = "stage1_airbox" / "stage2_no_grating" / "stage4_grating"
```

### 7.2 2D EUV 光栅命令示例

```bash
python3 -m src.runners.run_cases \
  --formulation port \
  --constraint-backend manual \
  --port-boundary-model dtn \
  --port-dtn-assembly auxiliary \
  --port-use-diffraction-orders \
  --polarization-type TM \
  --period-x 100 \
  --air-height 100 \
  --substrate-thickness 50 \
  --grating-width 50 \
  --grating-height 50 \
  --lambda0 13.5 \
  --mesh-target-size 1.0 \
  --mesh-cell-shape triangle \
  --compute-power-metrics
```

### 7.3 3D small-cell flat-layer sanity 示例

```bash
python3 -m src.runners.run_3d_cases \
  --stage-case stage4_flat_layer_sanity \
  --case normal \
  --period-x 10 \
  --period-y 10 \
  --air-height 5 \
  --substrate-thickness 5 \
  --lambda0 13.5 \
  --n-substrate 0.999002304859+0.00182649365j \
  --mesh-target-size 1.5 \
  --nedelec-degree 2 \
  --stage4-boundary-model dtn_port \
  --stage4-dtn-order-policy auto_propagating \
  --stage4-dtn-assembly auxiliary \
  --no-use-pml
```

### 7.4 3D block grating smoke 示例

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 10 \
  --nedelec-degree 1 \
  --stage4-boundary-model dtn_port \
  --stage4-dtn-order-policy zero_order
```

---

## 8. 文档结构

```text
docs/    # 任务流转：task.md / outcomes / review_report.md
notes/   # 理论笔记、使用说明、测试记录和代码阅读路线
src/     # 代码主体
results/ # 本地大结果，默认不提交 Git
```

重点文档：

```text
notes/README.md
notes/reference/current_version_boundaries.md
notes/reference/code_walkthrough.md
notes/quick_start/2d_euv_grating_dtn_usage_guide.md
notes/quick_start/stage2_2a_2b_2c_usage_guide.md
notes/quick_start/stage4_3d_block_grating_usage_guide.md
notes/theory/stage4_3d_dtn_port.md
notes/theory/stage4_3d_block_grating_diffraction.md
notes/theory/THEORY_RTA_AND_VOLUME_ABSORPTION.md
```

任务记录：

```text
docs/task000_review_code/
docs/task001_stage4_validation_cleanup/
docs/task002_rta_output_volume_absorption/
docs/task003_stage4_power_consistency/
docs/task004_small_cell_p_convergence_mpi_regression/
```

---

## 9. 当前开发边界

当前可以较有信心地认为：

```text
2D EUV DtN port 主线已形成可用验证链条；
3D staged framework 已经具备 Stage 1 / 2 / flat-layer sanity / block grating smoke 路径；
Stage 4 dtn_port + A_volume 主线在 small-cell flat-layer 中已能闭合；
p=2 在 small-cell flat-layer 中明显优于 p=1；
MPI 1/4/8 不改变 port/A_volume 主线结果；
全阶段 smoke regression 已完成。
```

当前不应过度声称：

```text
真实 100 nm 3D EUV grating 已完成物理收敛 benchmark；
probe_eh_fourier / net_flux 已能替代 port 作为主 R/T；
Stage 2B/2C 的粗网格 smoke 代表 PML/Fresnel 精度通过；
小电脑可以完成真实 grating 的 h≈1 nm 级别正式计算。
```

合并后推荐表述：

```text
当前版本完成 Stage 4 R/T/A 输出重构、A_volume 体吸收、flat-layer 解析参考、small-cell p 收敛、MPI 一致性与全阶段 smoke 回归。port + A_volume 是当前主线。
```

后续如果需要继续深入，建议另开任务研究：

```text
probe/net_flux 的采样与 curl 重构误差；
Stage 2B/2C 的精度验证；
高资源条件下真实 100 nm 3D EUV grating benchmark。
```
