# v2 文档索引

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

3. `parallel/parallel_v2_guide.md`
   需要 MPI 并行时看这个。它说明并行 Floquet、并行 `.vtu/.pvd` 输出、R/T 后处理和性能对比。

4. `theory/reflection_transmission_metrics.md`
   想理解反射率、透射率、衍射级次和能量守恒时看这个。

5. `theory/dtn_auxiliary_and_auto_orders.md`
   想理解 Fourier-DtN 端口、辅助变量法、自动衍射级和未来 3D 稀疏化路线时看这个。

6. `theory/solver_profiles_3d.md`
   想理解 3D 求解器 profile、direct/iterative 的区别、不收敛处理和矩阵统计时看这个。

7. `reference/code_walkthrough.md`
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
