# Stage 2：2A / 2B / 2C 使用和代码阅读指南

## 2026-06-22 更新：Stage 2 当前推荐验证口径

当前 Stage 2 三个解析验证 case 都使用 correction 口径，避免闭合周期盒在粗网格低阶离散下放大腔模：

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
