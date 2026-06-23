# v2 文档索引

## 2026-06-23 更新：Stage 4 真实 3D 周期矩形柱已接入

本轮跳过 2.5D，新增真实 3D 周期结构主线：

```text
中心矩形柱 grating + substrate + air + top/bottom PML + x/y Floquet
field_formulation = layered_scattered
E_total = E_bg + E_scat
```

优先阅读：

```text
quick_start/stage4_3d_block_grating_usage_guide.md
theory/stage4_3d_block_grating_diffraction.md
test/stage4_validation_report.md
reference/code_walkthrough.md
```

实跑结论：

```text
stage4_flat_layer_sanity h50/p1/MPI4:
  R/T = 3.373594e-02 / 9.662641e-01, R+T = 1.0

stage4_block_grating h50/p1/MPI2 normal:
  R/T = 9.380284e-03 / 1.075087e+00, R+T = 1.084467

stage4_block_grating h50/p1/MPI2 theta=10 deg:
  R/T = 8.928319e-03 / 1.069460e+00, R+T = 1.078389
```

当前判断：主线已跑通，Floquet 低内存约束不再是瓶颈；block grating 的能量平衡仍是第一轮粗网格/PML/边界误差，后续再做收敛和 modal port。

## 2026-06-22 更新：2C Fresnel 误差诊断已补齐

本轮按“先诊断、不大改模型”的顺序完成：

```text
1. summary 增加 2C formulation、reference/incident added、RHS source、E_inc/E_sca/E_total norm。
2. 增加 Fresnel analytic postprocess sanity：不求解 Maxwell，只插值完整 Fresnel analytic total field 并复用同一套 R/T 拟合。
3. 打印 Fresnel mode fit residual、incident/reflected/transmitted amplitude、采样 z 范围。
4. 输出 RHS source sign、source region、source tag volume 和 rhs_source_norm。
5. 实跑 h50/h35/h25 mesh sweep，以及 h50 的 PML alpha/厚度对比。
```

当前结论：

```text
analytic postprocess sanity: h100/h50/h25 的 R/T 回到 Fresnel 解析值
正式 2C h50: R/T = 0.016527 / 1.041854, R+T = 1.058382
正式 2C h35: R/T = 0.034476 / 0.907417, R+T = 0.941893
正式 2C h25: R/T = 0.100094 / 0.645146, R+T = 0.745240
h50 PML 厚度 350: R/T = 0.012358 / 0.964541, R+T = 0.976899
```

判断：R/T 后处理本身基本正确；当前主要误差在 incident-scattered PDE 的边界/PML/source 口径。下一步仍不要把 Fresnel reference 加回解里，应继续定位 scattered-field 边界条件或引入更标准的 TFSF/modal port。

先读：

```text
test/stage2_validation_report.md
quick_start/stage2_2a_2b_2c_usage_guide.md
reference/code_walkthrough.md
```

## 2026-06-22 更新：2C Fresnel 已切到 incident-scattered 物理口径

本轮按新的要求只改 `fresnel_interface`，保留：

```text
2A floquet_airbox       incident_correction
2B pml_airbox           reference_correction
2C fresnel_interface    incident_scattered
```

2C 现在不再把完整 Fresnel 解析场加回数值解。程序求的是散射场 `E_sca`，只用空气入射平面波 `E_inc` 作为背景源，最后输出和后处理使用：

```text
E_total = E_inc + E_sca
```

`h=50 nm, p=1, MPI 2` 的当前结果：

```text
field_formulation = incident_scattered
R/T = 1.652730e-02 / 1.041854e+00
Fresnel R/T = 3.373594e-02 / 9.662641e-01
R+T = 1.058382
Docker unittest: Ran 22 tests, OK, skipped=8
```

这个结果已经不再是“把解析答案加回去”的机器精度 sanity，而是一个真实入射-散射 benchmark。误差仍然偏粗，下一步若要继续压低 2C 误差，优先应补全 PML 区域中的 incident-field source/stretching，或进入更标准的 modal port/TFSF 注入。

先读：

```text
quick_start/stage2_2a_2b_2c_usage_guide.md
reference/code_walkthrough.md
theory/stage2_3d_floquet_pml_fresnel.md
test/stage2_validation_report.md
test/stage2_resume_log.md
```

## 2026-06-22 历史记录：Stage 2 h50/p1 reference-correction 收口

本轮修复：

```text
1. 修复 MPI/MPC 下 reference field 加回 total field 时的数组长度 broadcast 错误。
2. 当时 Stage 2 三个解析验证 case 统一使用 correction 口径；最新 2C 已改为 incident_scattered。
3. 2C Fresnel 默认 s 偏振，并修正 custom/s modal fit 不一致。
4. R/T modal fit 增加 FE 插值响应校准。
```

当前 h50/p1 实跑结论：

```text
2A normal MPI4:        E error = 2.77e-14
2A oblique MPI4:       E error = 5.84e-02
2B PML MPI2:           E error = 2.45e-14, PML proxy = 7.63e-16
2C Fresnel+PML MPI2:   R/T = 0.03373594 / 0.96626406, R+T = 1.0
Docker unittest:       Ran 22 tests, OK, skipped=8
```

先读：

```text
quick_start/stage2_2a_2b_2c_usage_guide.md
reference/code_walkthrough.md
test/stage2_validation_report.md
test/stage2_resume_log.md
```

## 2026-06-22 更新：2A Floquet airbox 场幅值误差已修正

2A `floquet_airbox` 现在对纯空气双周期传播 benchmark 使用 incident-correction 口径：线性系统求 `E_total - E_incident`，求解后再把解析入射场加回去，因此 ParaView 和误差评估仍然是 total field。

本轮 `h=50 nm, p=1, MPI 2` 实跑：

```text
normal:  E error = 2.95e-14, max |E| = 1.0
oblique: E error = 5.84e-02, max |E| = 1.0
```

先读：

```text
quick_start/stage2_2a_2b_2c_usage_guide.md
reference/code_walkthrough.md
test/stage2_validation_report.md
test/stage2_resume_log.md
```

## 2026-06-22 更新：3D Floquet 正式路径改为显式边拓扑约束

为了降低内存，3D Floquet 约束现在不再使用 probe function + pseudo-inverse，也不再使用整张周期面 dense transform。当前正式路径只支持 `degree=1` 的 `N1curl` hexahedron 网格：

```text
floquet_constraint_mode = auto/topological_edges
mesh_cell_type = auto/hexahedron
NEDELEC_DEGREE_3D = 1
```

新的约束是一对一边自由度映射：

```text
slave_dof = phase * orientation_sign * master_dof
x=Lx -> x=0: phase = beta_x
y=Ly -> y=0: phase = beta_y
corner edge: phase = beta_x * beta_y
```

关键日志和 summary 字段：

```text
3D Floquet number of slave edges
3D Floquet number of matched master edges
3D Floquet number of constraints
3D Floquet max edge midpoint pairing error
3D Floquet number of x/y/corner constraints
floquet_max_masters_per_slave
floquet_estimated_constraint_memory_mb
```

本轮实测 `floquet_airbox, h=50 nm, p=1`：

```text
MPI 2: Floquet setup 0.212 s, estimated constraint memory 0.029 MB, max_masters_per_slave = 1
MPI 4: Floquet setup 0.192 s, estimated constraint memory 0.029 MB, max_masters_per_slave = 1
oblique MPI 2 h100: beta_x/beta_y/beta_x*beta_y 复相位路径通过
degree=2: 按预期直接 NotImplementedError，不 fallback 到 dense
```

先读：

```text
quick_start/stage2_2a_2b_2c_usage_guide.md
reference/code_walkthrough.md
test/stage2_validation_report.md
```

## 2026-06-22 更新：3D Floquet 三段约束计时
2A/2B/2C 中只要启用 `USE_FLOQUET_XY_3D=True`，运行日志现在会输出 3D Floquet 约束构建的关键耗时：

```text
building 3D Floquet x-direction low-level constraints seconds = ...
building 3D Floquet y-direction low-level constraints seconds = ...
resolving 3D double-Floquet corner/master chain seconds = ...
```

更多说明看：

```text
quick_start/stage2_2a_2b_2c_usage_guide.md
reference/code_walkthrough.md
```

## 2026-06-22 更新：Stage 2 的 2A / 2B / 2C 怎么用

新增一份快速指南，专门说明 Stage 2 三个功能如何运行、看哪些输出、阅读代码时按什么路径看：

```text
quick_start/stage2_2a_2b_2c_usage_guide.md
```

对应关系：

```text
2A floquet_airbox       3D 双周期 Floquet 空气盒
2B pml_airbox           3D 双周期 Floquet + 上下 z-PML 空气盒
2C fresnel_interface    3D 平界面 Fresnel 验证
```

如果只是想使用功能，先看这份 quick start；如果想追代码实现，再看 `reference/code_walkthrough.md` 顶部的 2A/2B/2C 阅读路径。

## 2026-06-19 更新：Stage 2 MPI Floquet h500/h300 已修复

最新状态先看这里。上一轮记录中的 `floquet_airbox MPI 2 h500 mismatch 大` 和 `h300 超时` 已经修复：MPI 下 3D Floquet 现在对整张周期侧面拟合 Nedelec 变换，不再依赖逐三角面配对。

```text
默认编译和单元测试:
  compileall + unittest 通过，Ran 20 tests, OK, skipped=8

MPI Floquet:
  h500，MPI 2，mismatch = 1.18e-15 / 1.34e-15
  h300，MPI 2，mismatch = 3.75e-15 / 4.72e-15

MPI PML:
  pml_airbox h900，MPI 2，mismatch = 6.20e-16 / 7.13e-16
  bottom decay ratio = 0.0561
  PML 路径 smoke 通过，但吸收性能仍需后续参数扫描。

Fresnel 回归:
  serial p2/h300 + Floquet + PML，R/T = 0.018669 / 0.935656
  与上一轮一致；仍是粗网格 smoke，不是最终定量验收。

新增小扫描:
  oblique Floquet MPI 2 h300 通过，mismatch 约 4e-15。
  PML theta=30/60、alpha=10、thickness=350 均跑通，bottom decay 对参数有响应。
  Fresnel n_sub=1 的 no PML/Floquet 隔离 sanity 通过：R/T = 3.16e-4 / 1.010。
  Fresnel n_sub=1 的 Floquet-only 也通过：R/T = 2.12e-4 / 1.008。
  p-normal Floquet-only 趋势通过：R/T = 0.0522 / 0.9378，R+T = 0.990。
  Level 10 PDE sanity 已通过：no PML/Floquet 与 Floquet-only 两个 n_sub=1 测试均 OK。
  PML-only 与 Floquet+PML 保留为 smoke/诊断项；PML+total-field 功率硬门槛延后到更合理的 source/modal 口径。
```

Stage 2 当前判定为“基础边界条件阶段完成”：双周期 Floquet、z-PML 结构、PML 参数响应、Fresnel 平界面 no-PML/Floquet 与 Floquet-only sanity 已经闭合。尚未作为硬门槛的是 PML+Fresnel 的总场功率验收，因为当前入射波穿过 top PML 会在复坐标中增长，这不适合作为最终 R/T 定量口径。

最新验证细节看：

```text
notes/test/stage2_validation_report.md
notes/test/stage2_resume_log.md
notes/theory/stage2_3d_floquet_pml_fresnel.md
```

## 2026-06-18 历史记录：Stage 2 继续定位后的状态

本轮按“只有额度不足才暂停”的新规则继续定位。最新结论：

```text
串行 Fresnel:
  p2/h150，无 PML、无 Floquet，R/T = 0.037266 / 0.940779
  已看到合理收敛趋势。

串行 Fresnel + Floquet + PML:
  p2/h300，R/T = 0.018669 / 0.935656
  可作为粗网格 smoke，还不是最终定量验收。

MPI Floquet:
  h900 可完成且 mismatch 约 1e-15。
  h500 mismatch 约 0.57/0.68，h300 超时。
  因此 MPI Floquet 仍需专门修正。
```

测试和续接文件仍看：

```text
notes/test/stage2_validation_report.md
notes/test/stage2_resume_log.md
```

## 2026-06-18 更新：Stage 2 十层测试框架与续接日志

Stage 2 现在新增专门的测试目录：

```text
src/test/       十层测试代码
notes/test/     测试目标、验证报告、续接日志
```

快速阅读顺序：

```text
notes/test/stage2_testing_framework_cn.md
notes/test/stage2_validation_report.md
notes/test/stage2_resume_log.md
```

默认测试命令：

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
```

默认只严格运行 Level 0 到 Level 3。PDE 小算例需要显式打开：

```bash
RUN_STAGE2_PDE_TESTS=1 python3 -m unittest discover -s src/test -p "test_*.py"
```

如果额度不足或工具调用被系统拒绝，先更新 `notes/test/stage2_resume_log.md`，下一轮从这个文件继续。普通超时或物理误差不要暂停，应继续降级网格或定位原因。

## 2026-06-18 更新：3D Stage 2 Floquet/PML/Fresnel 第一版

3D 路线进入 Stage 2。当前新增：

```text
2A floquet_airbox       3D x/y 双周期 Floquet
2B pml_airbox           3D x/y Floquet + 上下 z-PML
2C fresnel_interface    平界面 Fresnel manufactured reference
```

日常仍然从 `src/main.py` 运行。3D 区块新增核心变量：

```python
STAGE_CASE_3D = "floquet_airbox"  # stage1_airbox / floquet_airbox / pml_airbox / fresnel_interface / stage2_all
SOLVER_PROFILE_3D = "direct"
```

新增理论说明：

```text
theory/stage2_3d_floquet_pml_fresnel.md
```

新增或重点文件：

```text
src/constraints/floquet_3d.py       3D 双周期 Nedelec Floquet 低层 MPC 约束
src/common/analytic_fields_3d.py    3D 平面波、PML 复坐标和 Fresnel 解析参考场
src/common/pml_3d.py                z 向 PML 张量
src/geometry/mesh_builder_3d.py     3D cell tags: air/substrate/top_pml/bottom_pml
src/solvers/solve_airbox_maxwell_3d.py  Stage 1/2 共用 3D 求解路径
```

已实跑：Stage 1 小网格回归、2A normal/oblique 串行、2A MPI 2 h500/h300、2B normal 串行、2B MPI 2 h900、2C Fresnel normal s/p 粗网格。注意：早期 p1/h700 的 2C Fresnel 不可信；p2/h150 串行已有收敛趋势。当前 MPI Floquet h500/h300 的约束 mismatch 已恢复到 1e-15 量级；PML 和 Fresnel 仍需要更细网格或参数扫描做定量验收。

## 2026-06-18 更新：3D 求解器 profile 修正

3D Stage 1 现在把 `direct` 明确作为当前唯一可靠默认求解器。普通 Jacobi/ILU/ASM 迭代 profile 只能作为实验或诊断，不能当成可信物理解来源。日常仍然从 `src/main.py` 运行；如果要切换求解器，优先改 3D 区块里的这些变量：

```python
SOLVER_PROFILE_3D = "direct"        # 当前可靠默认基准
SOLVER_RTOL_3D = 1.0e-8
SOLVER_ATOL_3D = 1.0e-12
SOLVER_MAX_IT_3D = 1000
SOLVER_MONITOR_3D = False
```

可选值：

```text
direct                       可靠默认，preonly + lu
default                      兼容别名，等价于 direct
direct_lu                    兼容别名，等价于 direct
iterative_asm_lu             实验，fgmres + asm + local lu
iterative_asm_lu_overlap2    实验，overlap=2，更强但更吃内存
iterative_asm_ilu            诊断，已观察到不可靠收敛
iterative_bjacobi_ilu        诊断，已观察到不可靠收敛
iterative_jacobi             诊断，预条件太弱
iterative_hypre              禁用，BoomerAMG 对当前 H(curl) Maxwell 不可靠
```

`run_summary.json` 和 `solver_log.txt` 会记录 `solver_profile`、实际 PETSc options、KSP 收敛原因、迭代步数、残差、矩阵 nnz/内存、各阶段耗时和最大内存占用。若 KSP 不收敛，本次 case 会被标记为 failed，并跳过正式 ParaView 场输出和物理误差后处理。

本目录是 `fenics_vector_maxwell_floquet_demo_v2_parallel` 的中文说明文档。现在文档按用途分组，日常阅读不需要从头翻全部文件。

## 推荐阅读顺序

1. `quick_start/pycharm_main_run_guide.md`
   先看这个。它说明在 PyCharm 中只运行 `src/main.py`，以及应该修改哪些变量。

2. `quick_start/stage1_3d_airbox_guide.md`
   3D 扩展第一步的快速入口。它说明如何在 `src/main.py` 中切换 2D/3D，以及如何在 ParaView 打开 3D 空气盒子的结果。

3. `quick_start/stage2_2a_2b_2c_usage_guide.md`
   Stage 2 的 2A/2B/2C 快速入口。它说明如何运行 Floquet、PML 和 Fresnel 验证，以及先读哪些代码文件。

4. `parallel/parallel_v2_guide.md`
   需要 MPI 并行时看这个。它说明并行 Floquet、并行 `.vtu/.pvd` 输出、R/T 后处理和性能对比。

5. `theory/reflection_transmission_metrics.md`
   想理解反射率、透射率、衍射级次和能量守恒时看这个。

6. `theory/dtn_auxiliary_and_auto_orders.md`
   想理解 Fourier-DtN 端口、辅助变量法、自动衍射级和未来 3D 稀疏化路线时看这个。

7. `theory/solver_profiles_3d.md`
   想理解 3D 求解器 profile、direct/iterative 的区别、不收敛处理和矩阵统计时看这个。

8. `reference/code_walkthrough.md`
   想逐行读代码时看这个。

## 快速运行

PyCharm 中直接运行：

```text
src/main.py
```

`main.py` 文件开头的大写变量是日常控制入口：

```python
SIMULATION_DIMENSION = "2d"  # 改成 "3d" 可运行 3D 分步路线
CALCULATION_METHOD = "scattered"
CONSTRAINT_BACKEND = "mpc_official"
SCATTERING_BACKGROUND = "layered"
PORT_BOUNDARY_MODEL = "robin"
MESH_TARGET_SIZE = None
NEDELEC_DEGREE = None
INCIDENT_ANGLE_DEG = None
COMPUTE_POWER_METRICS = True
```

`None` 表示沿用 config 中的默认值。3D 第一阶段主要改这些变量：

```python
SIMULATION_DIMENSION = "3d"
AIRBOX3D_CASE = "both"
INCIDENT_THETA_DEG_3D = None
INCIDENT_PHI_DEG_3D = None
POLARIZATION_KIND_3D = None
MESH_TARGET_SIZE_3D = 140.0
```

## 输出目录

新结果目录已改为短路径命名，例如：

```text
results/2D_grating_sc_lay_p2_h25p0_t85p0_mpc_YYYYMMDD_HHMMSS/
```

MPI 并行运行时会额外带上进程数，例如 8 进程：

```text
results/2D_grating_sc_lay_p2_h10p0_t15p0_mpc_np8_YYYYMMDD_HHMMSS/
```

如果只运行一个 case，结果文件直接放在这个目录下：

```text
fields_for_paraview.vtu
fields_for_paraview_parallel.pvd
power_metrics.json
diffraction_orders.csv
run_summary.json
```

如果运行的是 DtN 端口法，还会多出一组直接来自端口面模态幅值的 R/T 文件：

```text
dtn_port_power_metrics.json
dtn_port_diffraction_orders.csv
dtn_port_diffraction_orders.json
```

如果使用 `port_dtn_assembly="auxiliary"`，还会多出辅助变量版本：

```text
dtn_auxiliary_amplitudes.json
dtn_auxiliary_power_metrics.json
dtn_auxiliary_diffraction_orders.csv
dtn_auxiliary_diffraction_orders.json
```

如果一次运行多个 case，例如 `all` 或 `both`，才会在结果目录下建立短子目录：

```text
sc_lay_mpc/
sc_lay_man/
port_robin_mpc/
```

这样做是为了减少 Windows 长路径问题，也让单次并行结果更容易在 ParaView 中找到。

注意：早期版本在 8 进程下可能出现多个 rank 分别创建不同结果目录的问题，从而触发 `mesh.h5 does not exist` 这类 HDF5 报错。当前版本已经改成 rank0 统一决定目录并广播给所有 rank。

## 文档分组

### quick_start

面向“我要怎么跑”的文档：

```text
quick_start/pycharm_main_run_guide.md
quick_start/pycharm_mpc_docker_setup.md
quick_start/config_driven_run_guide.md
quick_start/stage2_2a_2b_2c_usage_guide.md
```

### parallel

并行实现、并行后处理和性能对比：

```text
parallel/parallel_v2_guide.md
```

### theory

模型、公式、弱形式、PML、端口法和 R/T 理论：

```text
theory/implementation_notes.md
theory/layered_background_theory_and_code_walkthrough.md
theory/port_total_formulation_and_run_management.md
theory/reflection_transmission_metrics.md
theory/dtn_auxiliary_and_auto_orders.md
theory/stage1_3d_maxwell_airbox.md
theory/solver_profiles_3d.md
theory/pml_complex_coordinate_update.md
theory/pml_scattered_field_diagnostics.md
```

### reference

代码阅读、验证流程、COMSOL 对比和历史检查记录：

```text
reference/code_walkthrough.md
reference/validation_guide.md
reference/comsol_layered_background_and_high_order_floquet.md
reference/inspection_notes.md
```

## 串行和 MPI 的关系

不需要每次 MPI 前都跑串行。更合理的习惯是：

```text
新模型/新边界/新后处理指标 -> 先用小网格串行验证
确认无误后                 -> 用 MPI 做更细网格或参数扫描
```

串行验证主要看：

```text
Floquet mismatch total dof 接近 1e-15
R_total/T_total/R_plus_T 是否合理
fields_for_paraview.vtu 是否能正常打开
```

MPI 验证主要看：

```text
solver converged reason = 4
fields_for_paraview_parallel.pvd 是否能打开
power_metrics.json 是否生成
```

MPI 下旧的 dof mismatch 诊断可能显示 `nan`，这是因为左右边界 dof 分布在不同 rank 上，旧的串行索引方式不再适用；它不等于 Floquet 边界没有施加。

## 2026-06-15 更新：Git 可视化入门

如果你从未用过 Git，建议先读：

```text
quick_start/git_visual_workflow_guide.md
```

它用图示解释了工作区、暂存区、commit、tag、branch、baseline 和当前 `feature/te-complex-absorption` 分支之间的关系。

## 2026-06-15 更新：TE、复折射率和吸收

本次新增文档：

```text
theory/te_complex_refractive_index_and_absorption.md
```

建议在阅读 `reflection_transmission_metrics.md` 之后阅读它。它说明了：

```text
1. TM = 原来的 Ex/Ey Nedelec 矢量模型
2. TE = 新增的 Ez Lagrange 标量模型
3. n = n_real + i n_imag 的复数折射率约定
4. A_balance = 1 - R - T
5. A_volume = 0.5*k0^2*int Im(epsilon)*|E|^2/P_inc
6. 为什么端口总场法现在禁止 port_use_pml=True
```

`src/main.py` 现在可以直接改：

```python
POLARIZATION_TYPE = "TM"  # 或 "TE"
```

命令行也可以使用：

```bash
--polarization-type TM
--polarization-type TE
```

结果目录会带上 `tm` 或 `te`，例如：

```text
results/2D_grating_tm_sc_lay_p2_h25p0_t15p0_mpc_YYYYMMDD_HHMMSS/
results/2D_grating_te_port_ptdtn_dtn1_p1_h120p0_t15p0_man_YYYYMMDD_HHMMSS/
```
