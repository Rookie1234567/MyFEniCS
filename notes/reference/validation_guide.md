# 准确性验证指南

本文说明如何验证当前空气-基座-光栅二维矢量 Maxwell 算例。

## 1. 验证不是标量 Helmholtz

检查 `src/solvers/solve_vector_maxwell.py`：

```python
curl_el = element("N1curl", msh.basix_cell(), cfg.nedelec_degree, dtype=default_real_type)
V = fem.functionspace(msh, curl_el)
```

这说明未知量在 `H(curl)` 空间中，使用 Nedelec 边单元。输出图也包含：

```text
Ex_real.png
Ex_imag.png
Ey_real.png
Ey_imag.png
E_vector_quiver_real.png
```

因此当前代码求的是二维复数电场矢量 `E=(Ex,Ey)`，不是一个标量场。

## 2. 验证几何

查看：

```text
results/air_substrate_grating_mpc_official/material_domains.png
```

应看到：

- 顶部和底部为 PML；
- 中间上方为空气；
- 下方一整层为基座；
- 基座上有一个居中的矩形光栅。

## 3. 验证入射场横向性

结果文件中：

```text
incident_transversality_dot_k_p = 4.441e-16
```

这对应：

```text
dot(k_vector, polarization_vector)
```

接近 0 说明入射电场和传播方向正交。

## 4. 验证 Floquet 约束

当前相位：

```text
phase = 0.0293627017155 + 0.999568822917 i
```

结果中：

```text
official total Floquet mismatch = 2.299e-15
manual   total Floquet mismatch = 2.277e-15
```

这个 mismatch 检查的是 Nedelec 边自由度意义下的：

```text
E_t_right - phase * E_t_left
```

接近机器精度说明左右周期约束正确施加。

## 5. 验证 PML 是否合理

当前 PML 的关键检查不是只看有没有吸收，而是看 PML 入口是否人为制造了新界面。

代码中应满足：

- 顶部 PML 使用空气材料延拓；
- 底部 PML 使用基座材料延拓；
- PML 复坐标使用官方 DOLFINx PML demo 的形式；
- 本项目先把 `y` 平移到物理区域中心，记为 `eta = y - y_center`，再使用

```text
eta' = eta + i * alpha / k0 * eta * (|eta| - l_dom/2) / (l_pml/2 - l_dom/2)^2
```

最后由 `grad((x, y'))` 得到 Jacobian，并生成 `epsilon_pml` 和 `mu_pml`。

对应实现位置：

```text
src/common/pml.py::top_pml_tensors
src/common/pml.py::bottom_pml_tensors
src/solvers/solve_vector_maxwell.py
```

查看：

```text
results/air_substrate_grating_mpc_official/E_scat_norm.png
```

应能看到散射场进入底部 PML 后逐渐衰减，不应在基座和底部 PML 的交界面出现一条强烈、硬性的高亮突变。注意 `E_total` 图在 PML 内不能作为主要判断依据，因为当前散射场公式把解析入射平面波加回输出，而 PML 主要用于吸收 `E_scat`。

## 6. 验证两个后端相互印证

查看：

```text
results/backend_comparison.json
```

当前结果：

```text
max_abs_E_total_difference = 1.998e-15
max_abs_E_scat_difference  = 3.353e-14
```

两个后端分别是：

- `dolfinx_mpc` 官方库约束装配；
- 手写矩阵消元 `C^H A C q = C^H b`。

二者结果差异在 `1e-14` 到 `1e-15` 量级，说明实现彼此一致。

## 7. 验证求解器

官方 `dolfinx_mpc` 版本：

```text
solver = dolfinx_mpc_lowlevel_add_constraint
ksp_converged_reason = 4
ksp_iterations = 1
dolfinx_mpc_num_local_slaves = 73
```

手写矩阵版本：

```text
solver = manual_constraint_elimination
num_reduced_dofs = 5280
reduced_linear_residual = 3.897e-14
```

这些数值说明两个系统都成功求解。

## 8. 验证场图

重点查看：

```text
results/air_substrate_grating_mpc_official/E_total_norm.png
results/air_substrate_grating_mpc_official/E_scat_norm.png
results/air_substrate_grating_mpc_official/E_vector_quiver_real.png
```

应能看到基座/光栅附近出现明显场调制，散射场非零，箭头图显示平面内电场方向。散射场图中底部 PML 内的场应整体衰减。

## 9. 和 COMSOL 对比什么

先确认单位约定。本项目默认入射场振幅为 1，因此电场是归一化电场。如果 COMSOL 中背景入射场设置为：

```text
E0 = 1[V/m]
```

那么本项目输出的 `E_total_abs` 数值可以直接按 `V/m` 理解。如果 COMSOL 中设置的是其他入射振幅，例如 `E0 = 1000[V/m]`，那么本项目结果需要乘以 1000 后再对比：

```text
E_physical[V/m] = E_code * E0[V/m]
```

如果已知入射光强 `I`，可用：

```text
E0 = sqrt(2 I / (n epsilon0 c))
```

把归一化电场换算成 `V/m`。

第一轮建议先对比这些量：

1. `|E_total|`：本项目输出为 `E_total_abs`，COMSOL 常见变量是 `normE` 或 `emw.normE`。
2. `Re(Ex)` 和 `Re(Ey)`：本项目输出为 `E_total_Ex_real`、`E_total_Ey_real`。相位约定一致时可以直接对比条纹位置。
3. `|E_scat|`：本项目输出为 `E_scat_abs`。它更适合检查 PML 吸收和结构附近散射强弱。
4. 固定高度处的 line cut：例如穿过光栅顶部、基座内部、空气区中部的水平线，比只看整张彩色图更容易判断是否一致。
5. 最大值和最小值位置：先看峰值是否出现在相近区域，不要一开始就追求完全相同的色标。

对比时建议只比较物理区域，也就是空气、基座和光栅区域，不把 PML 区域作为物理结果对比。PML 是数值吸收层，不同软件的 PML 变量定义和坐标拉伸方式可能不同。

ParaView 中打开：

```text
results/air_substrate_grating_mpc_official/fields_for_paraview.vtu
```

常用数组：

```text
E_total_abs          总电场模值，用来对比 COMSOL normE
E_scat_abs           散射场模值
E_total_real_vector  总场实部矢量，用来画箭头
E_total_imag_vector  总场虚部矢量
E_total_Ex_real      Ex 实部
E_total_Ex_imag      Ex 虚部
E_total_Ey_real      Ey 实部
E_total_Ey_imag      Ey 虚部
```

材料和区域数组是 cell data。当前只保存两个材料相关数组：

```text
domain_tag
material_id
```

按 `domain_tag` 筛选：

```text
1 air
2 substrate
3 grating
4 top_pml
5 bottom_pml
```

ParaView 操作路径：

```text
Filters -> Threshold -> Scalars 选择 domain_tag -> 设置范围 -> Apply
```

例如只显示空气，把范围设为 `1` 到 `1`；只显示光栅，把范围设为 `3` 到 `3`。

如果 COMSOL 和本项目的时间因子或入射相位原点不同，`Re(Ex)` 这类相位敏感图可能整体相移；这时应优先比较 `E_total_abs`、`E_scat_abs` 和 line cut 的包络形状。

## 10. 关于官方自动周期 helper

我实际运行过 `dolfinx_mpc.create_periodic_constraint_topological(...)`。当前版本报错：

```text
Periodic conditions for vector valued spaces are not implemented
```

因此对 Nedelec 矢量空间，本项目不能使用这个自动 helper。正式官方版本使用 `dolfinx_mpc.MultiPointConstraint.add_constraint(...)`，由本项目显式配对 Nedelec 边自由度并计算方向相位，随后由 `dolfinx_mpc` 完成约束装配和回代。

## 11. 下一步更严格验证

建议后续做：

- 网格收敛：把 `mesh_target_size` 从 `0.025` 降到 `0.020` 或 `0.015`；
- PML 扫描：改变 PML 厚度和 `pml_alpha`，检查物理区场是否稳定；
- 材料扫描：让 `n_grating` 和 `n_substrate` 不同，观察散射变化；
- 解析基准：用圆柱散射问题和 Mie 型解析解做定量验证。

## 12. 验证新增端口总场法

新增端口法的入口是：

```text
--formulation port_total
```

它和散射场法的主要区别是：未知量就是 `E_total`，而不是 `E_scat`。因此和 COMSOL 的端口激励结果对比时，优先比较：

```text
E_total_abs
E_total_Ex_real / E_total_Ex_imag
E_total_Ey_real / E_total_Ey_imag
```

端口法默认不使用上下 PML，边界条件改为：

```text
上端口：入射 Floquet 基模 + 允许向上反射的 Robin 端口
下端口：允许向下透射的 Robin 出射端口
左右边：Floquet 准周期边界
```

推荐验证命令：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation port_total --constraint-backend both --mesh-target-size 0.08 --visualization-degree 1"
```

应检查：

```text
1. run_summary.json 中 formulation = port_total_field
2. use_pml = false，除非你显式加了 --port-use-pml
3. floquet_mismatch_total_dof 接近 1e-15
4. mpc_official 和 manual 两个后端的 max(|E_total|) 很接近
5. fields_for_paraview.vtu 中存在 E_total_abs
```

注意：`port_boundary_model="robin"` 时，端口实现是单个 Floquet 基模 Robin 端口。如果 COMSOL 周期端口自动包含多个衍射级次，则应改用下面的 Fourier DtN 多级次端口。

现在已经提供了一个手写矩阵版 Fourier 多级次端口入口：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation port_total --constraint-backend manual --mesh-target-size 0.12 --visualization-degree 1 --port-order-count 1"
```

这个命令会包含 `m=-1,0,1` 三个 Floquet 级次。验证时看：

```text
run_summary.json 中 port_model = multi-order Fourier Floquet DtN port
port_boundary_model = dtn
port_dtn_order_count = 1
port_modes 中列出了 top/bottom 的每个 order、alpha、beta、q
reduced_linear_residual 接近 1e-14
floquet_mismatch_total_dof 接近 0
```

若要和 COMSOL 更严格对比，应把 `--port-order-count` 调到和 COMSOL 周期端口中启用的衍射级次数一致。

如果不想使用命令行，也可以直接改 `src/common/config.py`：

```python
calculation_method = "port"
constraint_backend = "manual"
port_boundary_model = "dtn"
port_dtn_order_count = 1
```

然后运行 `src/main.py`。配置式运行见：

```text
../quick_start/config_driven_run_guide.md
```

## 13. 验证反射率和透射率

每个算例目录现在应包含：

```text
power_metrics.json
diffraction_orders.csv
diffraction_orders.json
```

先看 `power_metrics.json`：

```text
R_total
T_total
R_plus_T
energy_residual_1_minus_R_minus_T
```

无损材料、足够细网格、衍射级次足够多、探针线远离近场时，应有：

```text
R_total + T_total 约等于 1
```

本次粗网格验证中：

```text
scattered layered: R+T 约 0.985650
port robin:        R+T 约 0.989875
port dtn:          R+T 约 0.997978
```

同一物理方法下 official/manual 的 R/T 差异约为 `1e-14`，说明后端一致。若要和 COMSOL 对比，建议优先比较 `port dtn` 的 `R_total`、`T_total` 和各级 `R_order/T_order`。

2026-06-09 后处理更新：新版 R/T 不再只用 `Ex` 做投影，而是先由

```text
Hz_scaled = (dEy/dx - dEx/dy) / i
```

恢复缩放后的磁场分量，再用每个 Floquet 级次里的 `Ex_m` 和 `Hz_m` 拆分向上波、向下波：

```text
Ex_down = 1/2 (Ex_m + Hz_m / Y_m)
Ex_up   = 1/2 (Ex_m - Hz_m / Y_m)
Y_m     = (k0 n)^2 / beta_m
```

因此现在检查能量守恒时，应同时看：

```text
R_plus_T
poynting_R_plus_T_from_net_flux
top_down_minus_incident_abs
bottom_up_Ex_abs
```

判断顺序建议为：

1. 先看同一物理方法下 `mpc_official` 和 `manual` 的 R/T 是否接近。
2. 再看 `R_plus_T` 是否接近 1。
3. 再看 `poynting_R_plus_T_from_net_flux` 是否和 `R_plus_T` 接近。
4. 如果仍有偏差，逐步加密 `mesh_target_size`，并增大 `diffraction_order_count` 与 `port_dtn_order_count`。
5. 如果使用散射场法带 PML，注意 PML 是数值吸收层，能量守恒检查应优先参考物理区域内的探测线和 DtN 端口法。

新版实际验证中，粗网格 `mesh_target_size=0.12` 的全组合结果仍有明显偏差，只能作为后端一致性检查；更细的 DtN 端口单案例更有参考价值：

```text
mesh_target_size = 0.06, port dtn manual:
R+T = 1.036683576
poynting_R_plus_T_from_net_flux = 1.018692855

mesh_target_size = 0.04, port dtn manual:
R+T = 0.991471291
poynting_R_plus_T_from_net_flux = 0.992615839
```

因此当前结论是：功率后处理已经朝能量守恒方向收敛，但定量对比 COMSOL 时不应使用 `0.12` 粗网格。建议至少使用 `mesh_target_size=0.04`，更严格时继续加密到 `0.03` 或 `0.025`。

## 14. 新 PML 复坐标公式后的默认全方法验证

2026-06-09 已把 PML 改为官方 DOLFINx demo 的复坐标形式，并重新运行 `config.py` 当前默认的全部方法。结果目录为：

```text
results/run_air_substrate_grating_all_bg_layered_port_all_dtn1_20260609_095504/
```

关键结果：

```text
scattered layered official: R+T = 1.001737492, Poynting = 1.001842494
scattered layered manual:   R+T = 1.001737492, Poynting = 1.001842494
port robin official:        R+T = 1.011355268, Poynting = 1.002585068
port robin manual:          R+T = 1.011355268, Poynting = 1.002585068
port dtn manual:            R+T = 1.002417199, Poynting = 1.002577824
```

其中散射场法和 DtN 端口法的能量守恒已经非常接近 1。Robin 端口的 `R+T` 略高一些，但直接 Poynting 通量诊断仍接近 1，这说明主要偏差来自 Robin 单模端口和模态投影统计，而不是 PML 改动导致求解失败。

同一物理方法下，official/manual 后端差异仍接近机器精度，因此新的 PML 公式没有破坏 Floquet 约束实现。
## 2026-06-15 更新：TE、复折射率和吸收验证

新增功能建议按下面顺序验证。

1. TM 无损回归：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation scattered \
  --constraint-backend manual \
  --polarization-type TM
```

确认旧 TM 路径仍能生成 `fields_for_paraview.vtu`、`power_metrics.json` 和 `run_summary.json`。

2. TE scattered：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation scattered \
  --constraint-backend manual \
  --polarization-type TE
```

确认输出中有：

```text
Ez_real.png
Ez_imag.png
E_total_norm.png
fields_for_paraview.vtu
```

ParaView 中应能看到 `E_total_Ez_real`、`E_total_Ez_imag`、`E_total_abs`。

3. TE official MPC：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation scattered \
  --constraint-backend mpc_official \
  --polarization-type TE
```

串行时可和 manual 比较最大场值；MPI 时优先用这个后端。

4. TE DtN port：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation port \
  --constraint-backend manual \
  --port-boundary-model dtn \
  --polarization-type TE
```

优先查看：

```text
dtn_port_power_metrics.json
```

其中无损材料时 `R_plus_T` 应比水平探测线 `power_metrics.json` 更接近 1。

5. 有损材料：

在 `src/common/config.py` 中设置：

```python
n_grating = 1.45 + 0.02j
```

然后重新运行。合理趋势是：

```text
R_total + T_total < 1
A_balance > 0
A_volume > 0
```

如果 `A_balance` 和 `A_volume` 不一致，先检查网格、端口级次数、探测线位置和材料虚部是否只加在真实材料区。

6. 端口 PML 禁用检查：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation port \
  --port-use-pml
```

程序应在装配前报错。当前这是预期行为，因为端口法还没有实现 PML 体积分。

## 2026-06-16 验证：DtN auxiliary 与自动衍射级

新增 auxiliary 后，建议用下面 5 个检查确认功能没有跑偏。

### Test 1：只使用 0 级

设置：

```python
PORT_BOUNDARY_MODEL = "dtn"
PORT_DTN_ASSEMBLY = "auxiliary"
PORT_USE_DIFFRACTION_ORDERS = False
```

或者命令行：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_cases \
  --formulation port \
  --constraint-backend manual \
  --port-boundary-model dtn \
  --port-dtn-assembly auxiliary \
  --no-port-use-diffraction-orders
```

`run_summary.json` 中应看到：

```text
port_orders_by_side = {"top": [0], "bottom": [0]}
```

### Test 2：自动衍射级

设置：

```python
PORT_USE_DIFFRACTION_ORDERS = True
```

当前默认参数、15 度入射、空气/基座折射率下，小网格验证得到：

```text
top    = [-1, 0]
bottom = [-1, 0, 1]
```

这是合理的，因为底部基座折射率更高，可以支持更多传播级次。

### Test 3：explicit 与 auxiliary 等价

分别跑：

```python
PORT_DTN_ASSEMBLY = "explicit"
PORT_DTN_ASSEMBLY = "auxiliary"
```

在同一组衍射级下，比较：

```text
dtn_port_power_metrics.json
max_abs_E_total
R_total
T_total
R_plus_T
```

本次粗网格验证结果：

| 方法 | 自动衍射级 | R_port | T_port | R+T_port |
|---|---:|---:|---:|---:|
| explicit | False | 0.020207960694 | 0.979792039306 | 1.000000000000 |
| auxiliary | False | 0.020207960694 | 0.979792039306 | 1.000000000000 |
| explicit | True | 0.025026127839 | 0.974973872161 | 1.000000000000 |
| auxiliary | True | 0.025026127839 | 0.974973872161 | 1.000000000000 |

### Test 4：auxiliary 幅值与 trace 投影一致

auxiliary 结果目录里会有：

```text
dtn_port_power_metrics.json
dtn_auxiliary_power_metrics.json
dtn_auxiliary_amplitudes.json
```

检查 `run_summary.json`：

```text
dtn_auxiliary_vs_trace_power_difference
```

其中 R/T/R+T 差值应接近 0。若差值明显不为 0，优先检查块系统符号和 `a_m=(1/L)ell_m^H u` 的归一化。

### Test 5：端口面法与水平探测线法

`power_metrics.json` 是水平探测线法，`dtn_port_power_metrics.json` 是端口面法。它们不一定完全相同，尤其粗网格时差异可能明显。与 COMSOL Periodic Port 对比时，优先使用端口面法；水平探测线法保留用于诊断内部均匀区域的场分解是否稳定。
