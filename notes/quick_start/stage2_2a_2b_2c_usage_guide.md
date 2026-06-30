# Stage 2：2A / 2B / 2C 使用和代码阅读指南

## 2026-06-30 更新：p=2 高阶 Floquet 已覆盖 2A / 2B / 2C

当前二阶 N1curl Floquet 的正式约束模式是：

```text
--nedelec-degree 2
--floquet-constraint-mode auto
resolved -> topological_trace_p2
```

已开放的 Stage 2 case：

```text
2A floquet_airbox
2B pml_airbox
2C fresnel_interface
```

仍未开放：

```text
Stage 4 grating p=2 Floquet
p>=3 Floquet
```

2B PML airbox p=2 示例：

```bash
python3 -m src.runners.run_3d_cases \
  --stage-case pml_airbox \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto

mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case pml_airbox \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto
```

2C Fresnel diagnostic p=2 示例：

```bash
python3 -m src.runners.run_3d_cases \
  --stage-case fresnel_interface \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto

mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case fresnel_interface \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto
```

阅读 p=2 代码时，先看：

```text
src/constraints/floquet_3d.py
  build_double_floquet_mpc(...)
  _resolve_constraint_mode(...)
  _build_double_floquet_mpc_p2_trace(...)
  _emit_block_constraint_rows(...)
```

其中 `_emit_block_constraint_rows(...)` 只让 owned slave dof 进入 `dolfinx_mpc.add_constraint()`；ghost slave dof 只保留诊断统计，避免 MPI 下重复约束同一个全局 trace dof。

## 2026-06-30 更新：Stage 2A 二阶 N1curl Floquet 运行方式

如果只想测试高阶 Floquet 约束，目前只运行 2A：

```bash
python3 -m src.runners.run_3d_cases \
  --stage-case floquet_airbox \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto
```

并行 smoke：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case floquet_airbox \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto
```

当前限制：

```text
p=2 只支持 floquet_airbox
p=2 不支持 pml_airbox / fresnel_interface / stage4_block_grating
p>=3 暂未实现
```

详细验证见：

```text
notes/test/3d_high_order_floquet_validation_report.md
```

## 2026-06-24 更新：Stage 2 无光栅代码入口已单独拆出

研究 2A/2B/2C 时，优先只看这一条路径：

```text
src/main.py
  ACTIVE_3D_INPUT_GROUP = "stage2_no_grating"
  Stage2NoGratingInputs3D(stage_case="floquet_airbox" / "pml_airbox" / "fresnel_interface")

src/runners/run_3d_airbox.py
  _stage_defaults(...)
  _run_stage_config(...)

src/solvers/solve_maxwell_3d_stage_2_no_grating.py
  run_stage2_no_grating_3d_case(...)

src/solvers/solve_maxwell_3d_common.py
  只在需要看统一有限元装配和诊断细节时进入。
```

`src/solvers/solve_airbox_maxwell_3d.py` 现在只是旧导入兼容层，不再作为 Stage 2 的主要阅读入口。

## 2026-06-22 更新：2C incident-scattered 诊断字段怎么用

运行 2C 后，先看 `run_summary.json` 里的这些字段，确认求解口径没有被意外改回 reference：

```text
field_formulation = incident_scattered
reference_added_to_solution = false
incident_added_to_solution = true
fresnel_reference_used_for_solution = false
fresnel_reference_used_for_comparison_only = true
```

再看 RHS 和模态拟合诊断：

```text
rhs_source_sign
rhs_source_region
rhs_source_tag_ids
rhs_source_tag_volumes
rhs_source_norm
E_inc_norm / E_sca_norm / E_total_norm
fresnel_top_mode_fit_residual
fresnel_bottom_mode_fit_residual
fresnel_incident_amplitude_abs
fresnel_reflected_amplitude_abs
fresnel_transmitted_amplitude_abs
fresnel_top_sampling_z_min/max
fresnel_bottom_sampling_z_min/max
```

本轮 analytic postprocess sanity 已经验证：把完整 Fresnel 解析场直接插值进同一个 Nédélec 空间后，h100/h50/h25 的 R/T 可以回到 Fresnel 解析值。因此当前 2C 的主要误差不在 R/T 后处理公式，而在 incident-scattered PDE/边界/PML 口径。

最新实跑表放在：

```text
notes/test/stage2_validation_report.md
```

## 2026-06-22 更新：2C Fresnel 现在是 incident-scattered physical benchmark

当前三个 Stage 2 case 的口径是：

```text
2A floquet_airbox       incident_correction      # 保持 2A sanity check
2B pml_airbox           reference_correction     # 暂时保持原 PML sanity check
2C fresnel_interface    incident_scattered       # 本轮改为物理 benchmark
```

运行 2C 时，数值解不再使用完整 Fresnel 解析场。程序只构造空气中的入射平面波 `E_inc`，求解散射场 `E_sca`，然后输出：

```text
E_total = E_inc + E_sca
```

检查 `run_summary.json` 时重点看：

```text
field_formulation = incident_scattered
incident_added_to_solution = true
reference_added_to_solution = false
fresnel_reference_used_for_solution = false
fresnel_reference_used_for_comparison_only = true
rhs_source_region = physical_substrate
rhs_source_norm
E_sca_norm / E_inc_norm / E_total_norm
R_total / T_total / R_plus_T
fresnel_R_error / fresnel_T_error
```

推荐 2C 命令：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case fresnel_interface \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

当前 h50/p1/MPI2 的 physical benchmark 结果约为：

```text
R/T = 1.65e-02 / 1.04
Fresnel R/T = 3.37e-02 / 9.66e-01
R+T = 1.058
```

这已经不是把解析答案加回去的 sanity test，所以不会再出现机器精度 R/T。当前主要剩余误差来自第一版 RHS 只在 physical substrate 加 source，bottom PML 暂时没有 incident-field stretching/source。后续若要继续压低 R/T 误差，优先改 PML scattered-field source 或引入 modal port/TFSF 注入。

## 2026-06-22 历史记录：上一版 Stage 2 reference-correction 口径

这一节记录的是上一版做 reference sanity check 时的口径。最新实现以上一节为准：2C `fresnel_interface` 已改成 `incident_scattered`，不再是 `reference_correction`。

当时 Stage 2 三个解析验证 case 都使用 correction 口径，避免闭合周期盒在粗网格低阶离散下放大腔模：

```text
2A floquet_airbox       field_formulation = incident_correction
2B pml_airbox           field_formulation = reference_correction
2C fresnel_interface    field_formulation = reference_correction
```

这意味着线性系统里的未知量是 correction field，ParaView、误差评估和 R/T 输出仍然使用重建后的 total field。MPC/MPI 下重建 total field 时，程序会在解函数自己的 `function_space` 里重新插值解析参考场，避免不同 rank 上本地数组长度不一致导致的 broadcast 错误。

2C 的默认偏振现在显式是 `s`；旧配置若还传 `custom`，Fresnel modal fit 也会按 s 基底处理，避免解析场和 R/T 拟合基底不一致。R/T 拟合还增加了有限元插值响应校准，所以 `h=50 nm, p=1` 的 Fresnel R/T 已能稳定回到解析值：

```text
2C Fresnel+PML h50 p1 MPI2:
  R/T = 3.373594e-02 / 9.662641e-01
  R+T = 1.000000e+00
```

推荐快速检查：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

2B/2C 的 `h=50 nm, p=1` PML direct LU 仍然会比较慢，单个 case 约 5 到 7 分钟、峰值内存约 4 GB。若只是确认功能，可以先用 `--mesh-target-size 100`；若要复现实测表，再用 h50。

## 2026-06-22 更新：2A airbox 改为 incident-correction 口径

2A `floquet_airbox` 现在不再直接求 total-field 齐次周期腔问题，而是只在纯空气 Floquet 传播验证中求：

```text
E_correction = E_total - E_incident
```

边界上令 `E_correction=0`，求解后再把解析入射场 `E_incident` 加回去输出。因此 ParaView、误差评估和 `run_summary.json` 中看到的仍然是 total E/H；只是线性系统里的未知量换成了 correction field。这个口径只对下面条件同时满足时启用：

```text
stage_case = floquet_airbox
geometry_kind = airbox
use_floquet_xy = True
use_pml = False
```

运行结束后看：

```text
field_formulation = incident_correction
```

本轮 `h=50 nm, p=1, MPI 2` 实跑结果：

```text
normal:
  relative_max_abs_E_error = 2.95e-14
  max |E| = 1.0

oblique:
  relative_max_abs_E_error = 5.84e-02
  max |E| = 1.0
```

这说明之前 2A 中约 10 倍的场幅值放大已经修正。H 误差仍明显大于 E，是因为当前 H 由低阶 E 的 curl 后处理得到，后续需要单独做 H 的网格/阶次收敛判断。

## 2026-06-22 更新：3D Floquet 已切换为显式边拓扑配对

现在 3D Floquet 正式约束路径不再使用 probe function + pseudo-inverse，也不再使用整张周期面 dense transform。当前第一版只支持：

```text
mesh_cell_type = auto/hexahedron
nedelec_degree = 1
floquet_constraint_mode = auto/topological_edges
```

约束形式固定为：

```text
slave_dof = phase * orientation_sign * master_dof
x=Lx -> x=0: phase = beta_x
y=Ly -> y=0: phase = beta_y
x=Lx 且 y=Ly 的角边: phase = beta_x * beta_y
```

如果 `nedelec_degree > 1`，程序会直接 `NotImplementedError`，不会 fallback 到 dense/pinv。运行后重点看这些新字段：

```text
floquet_constraint_mode_resolved = topological_edges
floquet_num_slave_edges
floquet_num_matched_master_edges
floquet_num_constraints
floquet_max_edge_midpoint_pairing_error
floquet_num_x_constraints
floquet_num_y_constraints
floquet_num_corner_constraints
floquet_max_masters_per_slave   # 应为 1
```

最新实跑结果：

```text
MPI 2, h=50 nm, p=1:
  x/y/corner constraints seconds = 0.200 / 0.009 / 0.001
  slave_edges = matched_master_edges = constraints = 832
  max_masters_per_slave = 1
  estimated_constraint_memory_mb = 0.029

MPI 4, h=50 nm, p=1:
  x/y/corner constraints seconds = 0.178 / 0.009 / 0.001
  slave_edges = matched_master_edges = constraints = 832
  max_masters_per_slave = 1

MPI 2, oblique, h=100 nm, p=1:
  beta_x、beta_y、beta_x*beta_y 均正确进入日志和约束。
```
## 2026-06-22 更新：Floquet 三段约束计时怎么看
现在运行 2A/2B/2C 时，只要打开了 `USE_FLOQUET_XY_3D=True`，终端日志会在构造 3D Floquet 约束时即时打印这几段耗时：

```text
building 3D Floquet x-direction low-level constraints seconds = ...
building 3D Floquet y-direction low-level constraints seconds = ...
resolving 3D double-Floquet corner/master chain seconds = ...
finalizing 3D double-Floquet MPC seconds = ...
3D Floquet total constraint setup seconds = ...
```

前三行就是最容易耗时和占内存的 Floquet 约束步骤。`x/y-direction low-level constraints` 主要在做周期侧面的 Nedelec 自由度采集、匹配和局部变换；`corner/master chain` 主要在处理双周期角点、边线和 master 链压缩；`finalizing` 是 `dolfinx_mpc` 真正接收并 finalize 约束的阶段。

跑完后也可以在输出目录的 `run_summary.json` 里查：

```text
floquet_constraint_timings_seconds
timings_seconds.floquet_build_x_constraints
timings_seconds.floquet_build_y_constraints
timings_seconds.floquet_resolve_corner_master_chains
timings_seconds.floquet_mpc_finalize
timings_seconds.floquet_total
```

并行运行时这些时间采用 MPI 所有 rank 的最大值，所以它反映的是最慢进程的耗时，更适合定位卡顿或内存不足发生在哪个阶段。


## 2026-06-22 更新：Stage 2 三个功能怎么用

Stage 2 分成三个小功能。它们共用同一套 3D 求解入口，不需要新建 `main_3d.py`：

```text
2A floquet_airbox       3D 双周期 Floquet 空气盒
2B pml_airbox           3D 双周期 Floquet + 上下 z-PML 空气盒
2C fresnel_interface    3D 平界面 Fresnel 验证
```

日常推荐先从 `src/main.py` 改变量运行；需要批量或 MPI 时，再用命令行。

## 1. 在 `src/main.py` 里运行

先确认 3D 开关：

```python
RUN_DIMENSION = "3D"
```

然后改 Stage 2 的核心变量：

```python
STAGE_CASE_3D = "floquet_airbox"      # 2A
STAGE_CASE_3D = "pml_airbox"          # 2B
STAGE_CASE_3D = "fresnel_interface"   # 2C
```

常用配套变量：

```python
AIRBOX3D_CASE = "normal"       # normal / oblique / both
MESH_TARGET_SIZE_3D = 300.0    # 单位 nm；越小越细，内存越高
NEDELEC_DEGREE_3D = 1      # 当前 3D Floquet 显式边拓扑约束只支持 degree=1
VISUALIZATION_DEGREE_3D = 1
SOLVER_PROFILE_3D = "direct"

INCIDENT_THETA_DEG_3D = None   # None 表示使用 preset；也可以填 30.0 / 60.0
INCIDENT_PHI_DEG_3D = None
POLARIZATION_KIND_3D = None    # s / p / custom
```

2B 和 2C 会用到 PML 参数：

```python
PML_TOP_THICKNESS_3D = 250.0
PML_BOTTOM_THICKNESS_3D = 250.0
PML_ALPHA_3D = 5.0
```

2C 会用到基底折射率：

```python
N_SUBSTRATE_3D = 1.45
```

运行后看 `results/` 里最新的 `3D_*` 目录。ParaView 优先打开：

```text
fields_3d_for_paraview.vtu
fields_3d_for_paraview_parallel.pvd   # MPI 运行时
```

重点看这些输出：

```text
run_summary.json
solver_log.txt
power_metrics_3d.json                 # 2C 有 R/T 时
```

## 2. 命令行运行

在 Docker 容器内的项目目录运行：

```bash
. dolfinx-complex-mode
```

2A：双周期 Floquet 空气盒：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case normal \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --mesh-target-size 300 \
  --solver-profile direct
```

2A 的斜入射：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case oblique \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --mesh-target-size 300 \
  --solver-profile direct
```

2B：Floquet + 上下 z-PML：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case pml_airbox \
  --case normal \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --mesh-target-size 900 \
  --pml-alpha 5 \
  --solver-profile direct
```

2B 的角度扫描例子：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case pml_airbox \
  --case normal \
  --incident-theta-deg 30 \
  --incident-phi-deg 0 \
  --polarization-kind s \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --mesh-target-size 900 \
  --solver-profile direct
```

2C：Fresnel 平界面：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case fresnel_interface \
  --case normal \
  --n-substrate 1.45 \
  --polarization-kind s \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --mesh-target-size 200 \
  --no-use-pml \
  --use-floquet-xy \
  --solver-profile direct
```

2C 的 `n_sub=1` sanity：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case fresnel_interface \
  --case normal \
  --n-substrate 1.0 \
  --polarization-kind s \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --mesh-target-size 200 \
  --no-use-pml \
  --use-floquet-xy \
  --solver-profile direct
```

MPI 运行示例：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case oblique \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --mesh-target-size 300 \
  --solver-profile direct
```

## 3. 2A 看哪些指标

2A 主要验证双周期 Floquet 约束。重点看：

```text
floquet_x_face_mismatch
floquet_y_face_mismatch
floquet_edge_corner_mismatch
max_face_pairing_coordinate_error
floquet_num_local_slaves
```

正常 smoke 结果中，`floquet_x_face_mismatch` 和 `floquet_y_face_mismatch` 应该接近 `1e-15` 到 `1e-12`。

ParaView 中主要看：

```text
E_V_per_m_*
H_A_per_m_*
domain_tag
```

## 4. 2B 看哪些指标

2B 主要验证 PML 网格、PML 张量和 PML 区域场衰减是否有合理响应。重点看：

```text
pml_reflection_proxy
pml_mode_fit_residual
pml_decay_ratio_top
pml_decay_ratio_bottom
pml_parameters
```

当前 2B 是 smoke/诊断口径。`pml_decay_ratio_bottom < 1` 表示向下出射方向有衰减。`pml_reflection_proxy` 目前不能单独作为最终吸收性能验收。

## 5. 2C 看哪些指标

2C 主要验证平界面 Fresnel 参考解和 R/T 后处理。重点看：

```text
R_total
T_total
R_plus_T
fresnel_R
fresnel_T
fresnel_R_error
fresnel_T_error
fresnel_top_mode_fit_residual
fresnel_bottom_mode_fit_residual
```

当前硬 sanity 是：

```text
n_sub=1.0
no PML/Floquet 或 Floquet-only
R≈0, T≈1
```

PML + Fresnel total-field 现在只作为 smoke/诊断项，不作为 Stage 2 硬门槛。原因是当前 total-field 入射波穿过 top PML 时会在复坐标中增长，后续应在 source/modal port 口径里重新定义 PML+功率验收。

## 6. 读代码路径

### 2A：Floquet airbox

```text
src/main.py
  读 3D 大写变量如何生成命令行参数。

src/runners/run_3d_airbox.py
  读 _stage_defaults("floquet_airbox") 如何打开 use_floquet_xy。

src/common/config_3d.py
  读 incident angles、kx/ky、floquet_phase_x/y。

src/geometry/mesh_builder_3d.py
  读 x/y/z 外边界 facet tags 如何生成。

src/constraints/floquet_3d.py
  2A 核心。读 build_double_floquet_mpc(...)。
  当前正式路径是显式 degree=1 N1curl mesh edge 配对：
  _build_edge_dof_map_p1(...)
  _build_constraints_for_kind(..., "x" / "y" / "corner")

src/solvers/solve_airbox_maxwell_3d.py
  读 build_double_floquet_mpc(...) 如何接入求解器，以及 summary 字段如何写出。
```

### 2B：PML airbox

```text
src/main.py
  读 PML_TOP_THICKNESS_3D、PML_BOTTOM_THICKNESS_3D、PML_ALPHA_3D。

src/runners/run_3d_airbox.py
  读 _stage_defaults("pml_airbox") 如何同时打开 use_floquet_xy 和 use_pml。

src/common/config_3d.py
  读 physical_z_min/max 与 domain_z_min/max 的区别。

src/geometry/mesh_builder_3d.py
  读 top_pml、bottom_pml cell tags 如何标记。

src/common/pml_3d.py
  2B 核心之一。读 z_stretch_derivative_value(...) 和 z_pml_tensors(...)。

src/common/analytic_fields_3d.py
  读 pml_complex_z(...) 如何给解析参考场做复坐标延拓。

src/solvers/solve_airbox_maxwell_3d.py
  读 _build_variational_forms(...) 中 top/bottom PML 体积分。
  读 _pml_probe_metrics(...) 中 PML 指标如何计算。
```

### 2C：Fresnel interface

```text
src/main.py
  读 N_SUBSTRATE_3D、POLARIZATION_KIND_3D、INCIDENT_THETA_DEG_3D。

src/runners/run_3d_airbox.py
  读 _stage_defaults("fresnel_interface") 如何设置 geometry_kind 和 n_substrate。

src/common/config_3d.py
  读 s/p polarization、direction_vector、substrate_index。

src/common/analytic_fields_3d.py
  2C 核心之一。读 fresnel_reference(...) 和 electric_field_code_values(...)。

src/geometry/mesh_builder_3d.py
  读 interface_z 如何进入 z-aligned mesh 和 substrate cell tag。

src/solvers/solve_airbox_maxwell_3d.py
  读 _fresnel_numerical_metrics(...) 如何拟合 R/T。
  读 _stage2_reference_metrics(...) 如何把 R/T 写入 summary。

src/test/test_10_stage2_combined.py
  读 n_sub=1 的 Stage 2 硬 sanity 测试。
```

## 7. 推荐学习顺序

```text
先跑 2A normal
再跑 2A oblique
再读 src/constraints/floquet_3d.py

再跑 2B normal
再改 theta / alpha / thickness
再读 src/common/pml_3d.py 和 _pml_probe_metrics(...)

最后跑 2C n_sub=1 sanity
再跑 2C n_sub=1.45 的 s/p、theta=0/30
再读 fresnel_reference(...) 和 _fresnel_numerical_metrics(...)
```
