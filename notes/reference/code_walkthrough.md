## 2026-06-15 更新：新增 TE 分支和吸收后处理

本次代码主线变为：

```text
TM scattered:
  src/main.py -> run_cases.py -> solve_vector_maxwell.run_case()

TM port:
  src/main.py -> run_cases.py -> solve_port_maxwell.run_port_case()

TE scattered:
  src/main.py -> run_cases.py -> solve_te_maxwell.run_te_case()

TE port:
  src/main.py -> run_cases.py -> solve_te_maxwell.run_te_port_case()
```

重点文件：

| 文件 | 新增作用 |
|---|---|
| `src/solvers/solve_te_maxwell.py` | 新增 TE 标量 `Ez` 求解器，包含 scattered、Robin port、DtN port。 |
| `src/constraints/floquet_scalar_constraint.py` | 新增标量 Floquet 手写消元约束。标量 Lagrange dof 没有 Nedelec 方向符号，因此只按 y 坐标配对并乘 Floquet 相位。 |
| `src/common/pml.py` | 新增 `top_scalar_pml_coefficients()` 和 `bottom_scalar_pml_coefficients()`，用于 TE scalar PML。 |
| `src/postprocessing/postprocess.py` | 新增 `save_scalar_fields_and_plots()`，输出 `Ez_real/Ez_imag/E_total_abs` 等 ParaView 数组。 |
| `src/postprocessing/power_metrics.py` | `compute_power_metrics()` 现在会根据 `cfg.polarization_type` 在 TM 和 TE 后处理之间分支，并输出吸收率。 |
| `src/runners/run_cases.py` | 新增 `--polarization-type`，输出目录名新增 `tm` 或 `te`。 |
| `src/main.py` | 新增 `POLARIZATION_TYPE`，PyCharm 直接运行时可切换 TM/TE。 |

TE 的弱式核心是：

```text
int grad(Ez) . conj(grad(v)) dOmega
- k0^2 int epsilon_r Ez conj(v) dOmega
```

TE scattered 右端项是：

```text
k0^2 int (epsilon_actual - epsilon_background) Ez_background conj(v) dOmega
```

TE 端口后处理中使用：

```text
Hx_scaled = dEz/dy / i
Ez_down = 1/2 (Ez_m - Hx_scaled_m / beta_m)
Ez_up   = 1/2 (Ez_m + Hx_scaled_m / beta_m)
```

端口总场法现在会显式禁止：

```text
port_use_pml=True
```

因为当前端口弱式只在 `air/substrate/grating` 上装配体积分，没有给 PML 单元装配 Maxwell/PML 项。直接禁止比生成一个看似正常但自由度悬空的结果更可靠。

# 当前代码讲解

本文对应当前空气-基座-光栅算例。代码主线是：

```text
配置参数 -> Gmsh 网格 -> 材料函数 -> Nedelec 空间
-> 入射场 -> Floquet 约束 -> Maxwell 弱式 -> 两种后端求解
-> 输出图像和 JSON 摘要
```

## 总公式

未知量是散射场：

```text
E_scat = (Ex, Ey)
```

总场为：

```text
E_total = E_inc + E_scat
```

二维 Maxwell 散射场方程：

```text
curl(curl(E_scat)) - k0^2 epsilon_r E_scat
  = k0^2 (epsilon_r - epsilon_air) E_inc
```

二维 in-plane curl：

```text
curl(E) = dEy/dx - dEx/dy
```

Floquet 条件：

```text
E(x + period_x, y) = exp(i kx period_x) E(x, y)
```

## `src/common/config.py`

| 行号 | 讲解 |
|---|---|
| 10-20 | `Tags` 定义物理标签：空气、基座、光栅、上下 PML、左右 Floquet 边界、外上下边界。 |
| 23-25 | `SimulationConfig` 是全部参数的集中入口。默认算例名为 `air_substrate_grating`。 |
| 27-38 | 设置纳米级几何和材料参数。虽然单位是 `um`，但 `0.30 um` 就是 `300 nm`。 |
| 40-44 | 设置 Nedelec 阶数、可视化阶数、网格目标尺寸、PML 吸收强度和标签。 |
| 46-56 | 根据折射率计算介电常数：`epsilon = n^2`。 |
| 58-68 | 计算角度、真空波数 `k0 = 2*pi/lambda0` 和角频率 `omega`。 |
| 70-80 | 计算向下传播斜入射波的 `kx`、`ky` 和偏振向量 `p`。 |
| 82-84 | 计算 Floquet 相位 `exp(i*kx*period_x)`。 |
| 86-104 | 计算总高度、物理区域上下边界、包含 PML 后的上下边界。 |
| 106-136 | 给出 x 方向周期边界、光栅左右边界、基座上下边界和光栅上下边界。 |
| 138-149 | 把参数整理为可写入 JSON 的格式。复数拆为 `[real, imag]`。 |
| 152-153 | 返回 demo 根目录。 |

## `src/geometry/mesh_builder.py`

| 行号 | 讲解 |
|---|---|
| 15-16 | 根据长度和目标网格尺寸估算 transfinite curve 节点数。 |
| 19-24 | 初始化 Gmsh 模型。 |
| 28-36 | 定义结构化分块坐标：x 方向为左边界、光栅左边、光栅右边、右边界；y 方向为下 PML、基座、光栅高度、上方空气、上 PML。 |
| 38-59 | 创建所有点、水平线和竖直线，并设置每段线的网格节点数。左右边界有相同纵向分段，方便 Floquet 配对。 |
| 61-67 | 准备按标签收集二维 surface。 |
| 68-79 | 遍历每个矩形小块，创建 surface。 |
| 81-95 | 给 surface 分类：最下层是 bottom PML，最上层是 top PML，基座层横向贯穿全周期，光栅只在中心列，其余是空气。 |
| 97-106 | 给二维区域添加 Gmsh physical group。 |
| 108-131 | 给左/右 Floquet 边界和上下外边界添加一维 physical group。 |
| 133-136 | 生成网格并转换为 DOLFINx mesh。 |
| 140-145 | 尝试写出 `mesh.xdmf`。 |

## `src/common/materials.py`

| 行号 | 讲解 |
|---|---|
| 10-13 | 创建 DG0 空间，每个单元一个常数介电常数。 |
| 14 | 所有单元先设为空气。 |
| 16-18 | 找到基座和光栅单元，分别写入 `eps_substrate` 和 `eps_grating`。 |
| 19 | 返回 `epsilon_r`。 |

## `src/common/pml.py`

| 行号 | 讲解 |
|---|---|
| 8-10 | 把二维 in-plane 场的 curl 写成三维向量 `(0,0,dEy/dx-dEx/dy)`。 |
| 13-14 | 把 `(Ex,Ey)` 扩展为 `(Ex,Ey,0)`。 |
| 17-22 | `_pml_coordinate` 实现官方 DOLFINx PML demo 中的复坐标公式 `x' = x + i alpha/k0 x (|x|-l_dom/2)/(l_pml/2-l_dom/2)^2`。 |
| 25-31 | `_y_pml_coordinate` 先把本项目的 y 坐标平移到物理区域中心，再套用官方公式，最后平移回原坐标。 |
| 34-40 | `_pml_tensors_from_coordinate_map` 对复坐标映射求 Jacobian，并由它得到各向异性的 `epsilon_pml` 和 `mu_pml`。 |
| 43-46 | 顶部 PML 使用空气介电常数，是空气向上的复坐标延拓。 |
| 49-52 | 底部 PML 使用基座介电常数，是基座向下的复坐标延拓。 |

## `src/constraints/floquet_constraint.py`

| 行号 | 讲解 |
|---|---|
| 14-21 | `FloquetConstraintData` 保存 slave dof、master dof、复系数、理论相位、方向符号和配对误差。 |
| 24-30 | `_facet_dof` 确认一阶 Nedelec 边界边只有一个边自由度。 |
| 33-52 | 读取左右边界 facet，按中点 y 坐标排序并配对。 |
| 54-62 | 构造探针场 `E_probe=(0, exp(i*kx*x))` 并插值到 Nedelec 空间。 |
| 70-81 | 对每对左右边求 `scale = dof_right(E_probe)/dof_left(E_probe)`。这个 scale 同时包含 Floquet 相位和 Nedelec 边方向符号。 |
| 83-90 | 返回约束数据。 |
| 93-120 | 手写矩阵消元：构造 `u=Cq`，求解 `C^H A C q = C^H b`，再恢复 `u`。 |
| 123-128 | 计算 Floquet mismatch：`||E_right-scale*E_left|| / characteristic_norm`。 |

## `src/solvers/solve_vector_maxwell.py`

| 行号 | 讲解 |
|---|---|
| 25-27 | 把 PETSc 矩阵转换为 SciPy CSR，供手写矩阵版本使用。 |
| 30-37 | JSON 序列化辅助函数。 |
| 40-52 | 构造入射场 `E_inc = p exp(i(kx x + ky y))`。 |
| 55-96 | 官方 `dolfinx_mpc` 后端。第 61 行创建 MPC 对象，第 67 行加入 slave/master/scale 约束，第 71-84 行用 `dolfinx_mpc.LinearProblem` 装配和求解。 |
| 99-147 | 官方自动周期 helper 探测后端。这个函数保留用于说明和测试，但当前 Nedelec 空间会触发 `Periodic conditions for vector valued spaces are not implemented`，所以不是正式运行后端。 |
| 150-158 | 手写矩阵后端调用 `solve_with_constraints`，返回 reduced residual。 |
| 161-184 | `run_case` 开始：创建输出目录、日志、检查 complex PETSc，并打印波矢、偏振和 Floquet 相位。 |
| 186-203 | 生成网格、创建 `N1curl` 空间、材料函数、入射场和 Floquet 约束数据。 |
| 205-211 | 创建 trial/test 函数和积分区域。物理区域包括空气、基座和光栅；顶部 PML 和底部 PML 分开积分。 |
| 213-214 | 生成顶部空气 PML 张量和底部基座 PML 张量。 |
| 215-223 | 建立 Maxwell 弱式。第 216-217 行是物理区 `curl curl - k0^2 epsilon E`；第 218-221 行分别加入顶部和底部 PML 贡献；第 223 行是散射源项。 |
| 225-232 | 选择官方 MPC 后端。正式双版本运行使用 `mpc_official`，不是 `mpc_auto`。 |
| 233-247 | 选择手写矩阵后端：装配完整矩阵和向量，再做消元。 |
| 251-253 | 计算总场 `E_total = E_inc + E_scat`。 |
| 255-259 | 输出图像和 VTX/BP 文件，并计算散射比、Floquet mismatch、耗时。 |
| 257-288 | 写入 `run_summary.json` 的内容。 |
| 290-305 | 写日志和 JSON 文件。 |

## `src/postprocessing/postprocess.py`

| 行号 | 讲解 |
|---|---|
| 13-15 | 创建离屏 PyVista plotter，适合 Docker 无显示器环境。 |
| 18-45 | 保存 `mesh.png` 和 `material_domains.png`。 |
| 48-63 | 把场转为 PyVista grid 并保存标量图。 |
| 66-84 | 保存总场实部箭头图。 |
| 88-112 | 给 ParaView 输出准备 point data：`E_total_abs`、`E_total_Ex_real`、`E_total_real` 等完整前缀数组。 |
| 115-130 | 给 ParaView 输出准备 cell data。目前只保存 `domain_tag` 和 `material_id`。 |
| 138-141 | 写入单位相关 field data：长度单位为 `um`，电场为入射振幅归一化单位。 |
| 144-162 | 保存单文件 `fields_for_paraview.vtu`。这是当前推荐打开的 ParaView 文件。 |
| 165-185 | 把 Nedelec 场插值到 DG 向量空间，写出 `E_inc.bp`、`E_scat.bp`、`E_total.bp`。 |
| MPI 分支 | 并行运行时额外写出 `fields_for_paraview_parallel.pvd` 和 `fields_for_paraview_rankXXXX.vtu`。在 ParaView 中打开 `.pvd` 可看到完整分布式结果。 |
| 192-194 | 计算 `|E| = sqrt(|Ex|^2 + |Ey|^2)`。 |
| 196-198 | 调用 ParaView 输出函数写入场和材料数组。 |
| 200-213 | 保存 Ex/Ey 实虚部、总场模值、散射场模值、相位和箭头图。 |
| 215-219 | 返回最大场强指标。 |

## `src/main.py`

| 行号 | 讲解 |
|---|---|
| 1-8 | 导入 `sys` 和 `Path`，为 PyCharm 直接以脚本方式运行做准备。 |
| 16-52 | PyCharm 直接运行时最常改的控制变量，例如 `CALCULATION_METHOD`、`CONSTRAINT_BACKEND`、`MESH_TARGET_SIZE`、`INCIDENT_ANGLE_DEG`。 |
| 55-66 | 自动把 v2 项目的上一级目录加入 `sys.path`，这样直接运行 `src/main.py` 也能正确导入包。 |
| 69-102 | 把上面的 Python 变量转换成和命令行完全一致的参数列表。 |
| 105-116 | 如果没有命令行参数，就使用 PyCharm 控制变量；如果有 `--help` 或其他命令行参数，就交给 `src/runners/run_cases.py` 正常解析。 |

## 两个单独入口

| 文件 | 作用 |
|---|---|
| `src/runners/run_grating_mpc_official.py` | 只运行官方 `dolfinx_mpc` 约束装配版本。 |
| `src/runners/run_grating_manual.py` | 只运行手写矩阵消元版本。 |

## `Dockerfile.mpc` 和脚本

| 文件 | 讲解 |
|---|---|
| `Dockerfile.mpc` | 基于 `ghcr.io/jorgensd/dolfinx_mpc:v0.10.5`，额外安装 `pyvista`。 |
| `run_demo_mpc.sh` | 如果镜像不存在就构建，然后运行 `run_cases --constraint-backend both`。 |
| `run_demo.sh` | 使用原 `code-dolfinx` compose 环境，只跑手写矩阵版本。 |

## 最重要的自检点

1. `solve_vector_maxwell.py` 第 191 行仍然是 `N1curl`。
2. `solve_vector_maxwell.py` 第 209 行物理域包含 `air/substrate/grating`。
3. `solve_vector_maxwell.py` 第 210-214 行把 top PML 和 bottom PML 分开，并分别使用空气和基座背景材料。
4. `solve_vector_maxwell.py` 第 216-223 行仍然是 Maxwell 散射场弱式。
5. `floquet_constraint.py` 第 70-81 行仍然用探针场处理 Nedelec 方向符号。
6. `run_summary.json` 里的 `floquet_mismatch_total_dof` 应接近 `1e-15`。
7. `backend_comparison.json` 里的两个后端最大场强差应接近 `1e-14` 量级。

## 2026-06-09 代码补充：端口总场法

本文件前面的讲解以原来的散射场法为主。现在新增了端口总场法，代码主线变成：

```text
散射场法：src/main.py -> run_cases -> solve_vector_maxwell.run_case
端口法：  src/main.py -> run_cases -> solve_port_maxwell.run_port_case
```

新增或改动的文件如下。

| 文件 | 新增作用 |
|---|---|
| `src/solvers/solve_port_maxwell.py` | 直接求解 `E_total`，可选择 Robin 基模端口或 Fourier DtN 多级次端口。 |
| `src/common/output_paths.py` | 为每次运行生成带时间戳的唯一结果目录。 |
| `src/main.py` | PyCharm 直接运行入口；文件开头的大写变量会转换成运行参数，再调用 `src/runners/run_cases.py`。 |
| `src/common/config.py` | 集中定义运行选择、材料、几何、端口模型、DtN 级次数、唯一输出目录等参数。 |
| `src/geometry/mesh_builder.py` | 根据 `use_pml` 决定是否生成上下 PML 区域；上下外边界仍保留为端口边界标签。 |
| `src/runners/run_grating_manual.py` | 仍只运行手写矩阵版，但输出目录改为唯一目录。 |
| `src/runners/run_grating_mpc_official.py` | 仍只运行官方 MPC 版，但输出目录改为唯一目录。 |

端口法求解的强形式可以简写为：

```text
curl curl(E_total) - k0^2 epsilon_r E_total = 0
```

端口边界把上方入射波写入右端项。对当前二维 in-plane 电场，边界上的简化关系可写成：

```text
top:    curl(E_total) + q_air E_total,x = 2 q_air E_inc,x
bottom: curl(E_total) - q_sub E_total,x = 0
```

其中：

```text
q_air = -i k_air^2 / beta_air
q_sub = -i k_sub^2 / beta_sub
beta = sqrt(k^2 - kx^2)
```

完整的强形式、弱形式、端口符号为什么这样取，以及 `solve_port_maxwell.py` 的逐行讲解，见：

```text
../theory/port_total_formulation_and_run_management.md
```

如果命令行加入：

```text
--port-order-count N
```

会临时覆盖 `config.py` 里的 `port_dtn_order_count`。更推荐直接在 `config.py` 中设置：

```python
port_boundary_model = "dtn"
port_dtn_order_count = N
```

`solve_port_maxwell.py` 会额外启用下面几个函数：

| 函数 | 作用 |
|---|---|
| `_fourier_trace_vector` | 在端口边界上装配 `∫ exp(i alpha_m x) conj(v_x) ds`，得到每个 Floquet 级次的 trace 向量。 |
| `_sparse_outer_trace` | 用 trace 向量构造低秩端口矩阵块，避免把整个有限元矩阵做成稠密矩阵。 |
| `_add_fourier_port_operators` | 对上、下端口的 `m=-N...N` 级次求和，把非局部 Fourier 端口算子加到矩阵和右端项里。 |

多级次端口目前只支持：

```text
--constraint-backend manual
```

现在 `run_cases.py` 的默认值来自 `SimulationConfig`，也就是：

```python
calculation_method
constraint_backend
scattering_background
port_boundary_model
port_dtn_order_count
unique_output
```

所以 PyCharm 中可以只运行模块，不填参数。完整配置式运行说明见：

```text
../quick_start/config_driven_run_guide.md
```

## 2026-06-09 代码补充：反射率和透射率后处理

新增文件：

```text
src/postprocessing/power_metrics.py
```

它从 `E_total` 统一计算散射场法和端口总场法的：

```text
R_total
T_total
R_m / T_m
反射/透射复振幅相位
```

`solve_vector_maxwell.py` 和 `solve_port_maxwell.py` 都会调用：

```python
compute_power_metrics(mesh_data, cfg, E_total, out_dir)
```

所以两种求解方法输出同样格式的：

```text
power_metrics.json
diffraction_orders.csv
diffraction_orders.json
```

`run_cases.py` 会把每个 case 的 R/T 汇总进：

```text
backend_comparison.json
```

最常用的新命令是：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation port_total --constraint-backend both"
```

### 新版 `power_metrics.py` 的关键步骤

新版功率后处理的核心不是只看 `Ex`，而是先恢复缩放后的磁场：

```text
Hz_scaled = (dEy/dx - dEx/dy) / i
```

代码中对应的主要函数是：

```python
_line_field_and_scaled_hz(...)
```

早先临时尝试过在探测线附近用点值有限差分近似导数，但粗网格下误差偏大。现在正式实现改成：用 UFL 对有限元函数直接写出

```text
(dEy/dx - dEx/dy) / i
```

并把它插值到 DG 空间，生成 `Hz_scaled`。这样 `Hz` 来自有限元函数本身的单元内导数，而不是额外的点值差分。

采样 `E` 和 `Hz_scaled` 时，因为左右边界是 Floquet 准周期边界，靠近周期边界的横向坐标仍然要补上相位：

```text
E(x + period, y) = exp(i kx period) E(x, y)
```

这部分由：

```python
_wrap_x_values(...)
_sample_field_on_wrapped_line(...)
```

处理。

随后代码对 `Ex` 和 `Hz_scaled` 同时做 Fourier 投影：

```text
Ex_m = mean(Ex exp(-i alpha_m x))
Hz_m = mean(Hz exp(-i alpha_m x))
```

并用模态导纳：

```text
Y_m = (k0 n)^2 / beta_m
```

拆分上下行波：

```text
Ex_down = 1/2 (Ex_m + Hz_m / Y_m)
Ex_up   = 1/2 (Ex_m - Hz_m / Y_m)
```

顶部空气线上的 `Ex_up` 用来算反射，底部基座线上的 `Ex_down` 用来算透射。每个传播级次的功率为：

```text
P_m = period * 1/2 * Re(Y_m) * |Ex_m|^2
```

所以 `power_metrics.json` 里的：

```text
R_total
T_total
R_plus_T
```

现在来自 `Ex+Hz` 的模态功率，而不是旧版的单独 `Ex` 估算。

同时还会保存直接 Poynting 通量诊断：

```text
poynting_R_plus_T_from_net_flux
top_flux_y_weighted
bottom_flux_y_weighted
```

如果 `R_plus_T` 和 `poynting_R_plus_T_from_net_flux` 都接近 1，说明功率守恒比较可信；如果二者互相差很多，优先检查网格、探测线位置、衍射级次数和边界条件。

## 2026-06-15 代码补充：DtN 端口面 R/T 后处理

本次新增的目标是：当端口法使用 `port_boundary_model="dtn"` 时，除了保留原来的水平探测线 R/T，还要直接复用 DtN 端口矩阵中的边界积分投影向量，计算一组端口模态 R/T。

主要改动在：

```text
src/postprocessing/power_metrics.py
src/solvers/solve_port_maxwell.py
```

### `power_metrics.py`

新增函数：

```python
compute_dtn_port_power_metrics(mesh_data, cfg, E_total, out_dir)
```

它只在 DtN 端口法中使用，输出：

```text
dtn_port_power_metrics.json
dtn_port_diffraction_orders.csv
dtn_port_diffraction_orders.json
```

计算步骤是：

```text
1. DtN 端口矩阵装配时，对每个级次 m 已经生成 ell_m 边界积分向量
2. 代码马上把 dense ell_m 压缩成 indices + values
3. 后处理复用压缩 ell_m，对有限元解向量 u 做内积，得到 Ex_top,m 和 Ex_bottom,m
4. 上端口：Ex_top,m 减去已知入射基模，得到反射模态幅值
5. 下端口：Ex_bottom,m 直接作为透射模态幅值
6. 用 Y_m = (k0 n)^2 / beta_m 把模态幅值转换成功率
```

对应公式：

```text
ell_m,j = ∫_port exp(i alpha_m x) conj(phi_j,x) ds
Ex_m = (1/period) sum_j u_j conj(ell_m,j)
R_amp,m = [Ex_top,m - delta_m0 Ex_inc,m] exp(-i beta_top,m y_top)
T_amp,m = Ex_bottom,m exp(i beta_bottom,m y_bottom)
P_m = period * 1/2 * Re(Y_m) * |amplitude_m|^2
```

这样做比“在端口附近再画一条采样线”更干净，因为后处理和 DtN 边界条件使用同一个投影算子，避免了额外点采样、插值和边界碰撞判断误差。

### 压缩 trace 向量

早期代码为了写起来简单，曾经直接保存：

```python
trace_vectors[side][order] = ell.copy()
```

其中 `ell` 是完整 dense 向量，长度等于整个有限元空间的自由度数。大规模算例中这个做法不合适，因为端口 trace 向量的非零项只集中在端口边界自由度附近。

现在代码改为：

```python
trace = _compress_trace_vector(ell)
trace_vectors[side][order] = trace
```

`trace` 内部只保存：

```text
indices  非零自由度编号
values   非零复数值
size     原始 dense 长度
cutoff   压缩阈值
```

矩阵外积由：

```python
_compressed_outer_trace_triplets(trace, coefficient)
```

生成 COO 三元组。它不再访问完整 `ell`，而是直接使用：

```text
rows = repeat(indices)
cols = tile(indices)
data = coefficient * values_i * conj(values_j)
```

早期写法是每个端口、每个级次都先生成一个稀疏矩阵，然后反复做：

```python
A_port = A_port + A_mode
```

这会制造很多中间稀疏矩阵副本。现在改为把所有级次的 `rows/cols/data` 暂存在列表里，最后一次性构造：

```python
A_port = sparse.coo_matrix((all_data, (all_rows, all_cols)), shape=A_csr.shape).tocsr()
```

这样总的非零项数学上不变，但减少了多次稀疏矩阵相加带来的临时内存峰值。

入射端口源项也使用：

```python
_add_compressed_trace_to_rhs(...)
```

只更新 `b_out[indices]`。DtN 端口 R/T 后处理同样只用压缩向量：

```text
Ex_m = (1/period) sum(solution[indices] * conj(values))
```

运行摘要 `run_summary.json` 的 `port_modes` 中会记录：

```text
num_trace_dofs
port_outer_nnz
dense_trace_size
trace_compression_ratio
trace_vector_storage
trace_cutoff
```

这些字段可以用来确认压缩是否生效。比如小网格验证中，`dense_trace_size=433`，`num_trace_dofs=8`，`port_outer_nnz=64`，压缩比例约为 `0.0185`。

### ParaView 后处理网格复用

早期 `postprocess.py` 在保存 ParaView 数据时，会为 `E_total`、`E_scat`、`E_inc` 各调用一次：

```python
plot.vtk_mesh(V_dg)
```

这会重复生成同一个 DG 可视化网格的拓扑、单元类型和坐标数组。现在改成：

```python
grid, coords = _field_grid(V_dg)
total_values = _field_values(E_total_dg, grid.n_points)
scat_values = _field_values(E_scat_dg, grid.n_points)
inc_values = _field_values(E_inc_dg, grid.n_points)
```

也就是可视化网格只构造一次，三个场只读取各自的系数数组。输出文件内容不变，但大网格后处理时少了两份重复的 VTK 网格临时数组。

### `solve_port_maxwell.py`

端口法求解完成后仍然先调用：

```python
power_metrics = compute_power_metrics(mesh_data, cfg, E_total, out_dir)
```

这会生成原来的水平探测线结果。

如果当前端口模型是 DtN，`_add_fourier_port_operators(...)` 会返回 `port_trace_vectors`，随后额外调用：

```python
dtn_port_power_metrics = compute_dtn_port_power_metrics(
    mesh_data, cfg, E_total, out_dir, port_trace_vectors
)
```

并把结果写进 `run_summary.json`：

```text
power_metrics                         水平探测线法
dtn_port_power_metrics                DtN 端口面法
dtn_port_vs_probe_power_difference    端口面法减去水平线法的 R/T 差值
```

因此，同一个 DtN 结果目录里现在会同时看到两套 R/T 数据。和 COMSOL 的 Periodic Port 对比时，优先看 `dtn_port_power_metrics.json`；调试内部场分解和采样线稳定性时，再看 `power_metrics.json`。
# v2 代码阅读提示

v2 已经把旧版 `src` 里的代码按功能拆开。阅读时建议先看：

```text
src/common/config.py
src/geometry/mesh_builder.py
src/constraints/floquet_constraint.py
src/solvers/solve_vector_maxwell.py
src/solvers/solve_port_maxwell.py
src/postprocessing/power_metrics.py
src/postprocessing/postprocess.py
src/runners/run_cases.py
```

顶层 `src` 现在只保留 `main.py` 作为 PyCharm/命令行统一入口，真正实现已经移动到各功能子目录。并行 Floquet 的重点在 `src/constraints/floquet_constraint.py`：MPI 下每个 rank 只约束自己拥有的右边界 slave，自由度 master 使用全局编号和 owner rank。

## 2026-06-16 代码补充：DtN 辅助变量法

这次主要改动在三个文件。

### `src/common/config.py`

新增三个配置：

```python
port_dtn_assembly: str = "auxiliary"
port_use_diffraction_orders: bool = False
port_rayleigh_tolerance: float = 1.0e-6
```

`port_dtn_assembly` 控制 DtN 端口装配方式：

```text
explicit   旧的显式外积 Q^*YQ 方法
auxiliary  新的辅助变量块系统方法
```

`port_use_diffraction_orders=False` 时只选 0 级；`True` 时自动选择上、下端口各自明确传播的衍射级。

### `src/solvers/solve_port_maxwell.py`

阅读顺序建议如下。

1. `_select_dtn_port_modes(...)`

这个函数根据：

```text
alpha_m = kx + 2*pi*m/L
|alpha_m| < n_j*k0
```

分别判断顶部和底部哪些级次传播，并把候选级次、是否传播、是否接近 Rayleigh anomaly 写入 metadata。

2. `_build_dtn_trace_data(...)`

这个函数对选中的每个端口级次生成压缩投影向量：

```text
ell_m,i = integral_Gamma exp(i alpha_m x) conjugate(phi_i,x) dGamma
```

只保存非零自由度编号 `indices` 和对应复数值 `values`，避免保存完整 dense 向量。

3. `_add_fourier_port_operators_explicit(...)`

这是旧方法的新入口。它仍然装配：

```text
A_port,m = (q_m/L) ell_m ell_m^H
```

主要用于和新方法对照。

4. `_add_fourier_port_operators_auxiliary(...)`

这是新增方法。它引入辅助未知量 `a_m`：

```text
A u + q_m ell_m a_m = b
a_m - (1/L) ell_m^H u = 0
```

矩阵是块系统：

```text
[ A   B ] [ u ] = [ b ]
[ C   I ] [ a ]   [ 0 ]
```

消去 `a` 后会回到 explicit 的外积形式，因此两者应当给出相同解。

5. `_solve_manual_with_auxiliary(...)`

这个函数把 Floquet 约束只施加到有限元自由度 `u` 上，对辅助变量使用单位矩阵：

```text
C_aug = block_diag(C_fem, I_aux)
```

然后求：

```text
C_aug^H A_aug C_aug x = C_aug^H b_aug
```

### `src/postprocessing/power_metrics.py`

新增的共同计算核心是：

```python
_compute_tm_dtn_power_from_coefficients(...)
```

它只需要顶部和底部的端口模态幅值字典：

```python
top_ex_coeff[order]
bottom_ex_coeff[order]
```

然后按同一套公式计算 R/T。

`compute_dtn_port_power_metrics(...)` 从压缩 trace 向量重新计算：

```text
a_m = (1/L) ell_m^H u
```

`compute_dtn_auxiliary_power_metrics(...)` 直接读取辅助未知量 `a_m`。这两组结果在小模型中应当一致；如果不一致，优先检查块系统符号、端口投影归一化和线性求解残差。

### 小验证结论

粗网格验证中：

```text
explicit + 0级:    R+T = 1.000000000000
auxiliary + 0级:   R+T = 1.000000000000
explicit + auto:  R+T = 1.000000000000
auxiliary + auto: R+T = 1.000000000000
```

同一组衍射级下，explicit 和 auxiliary 的端口面 R/T 完全一致到显示精度。
