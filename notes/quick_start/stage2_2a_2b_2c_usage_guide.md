# Stage 2：2A / 2B / 2C 使用和代码阅读指南

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
NEDELEC_DEGREE_3D = 2
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
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --mesh-target-size 300 \
  --solver-profile direct
```

2A 的斜入射：

```bash
python3 -m src.runners.run_3d_airbox \
  --stage-case floquet_airbox \
  --case oblique \
  --nedelec-degree 2 \
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
  --nedelec-degree 2 \
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
  --nedelec-degree 2 \
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
  串行看 _axis_raw_maps(...)。
  MPI 看 _axis_raw_maps_plane(...)。

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
