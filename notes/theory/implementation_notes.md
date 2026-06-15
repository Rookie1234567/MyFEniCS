# 实现记录

## 几何

当前算例是一个二维周期单元：

- 上方为空气；
- 下方有横向贯穿整个周期的基座；
- 基座上放置一个矩形光栅条；
- 上下分别加 PML；
- 左右为 Floquet 准周期边界。

默认尺寸均以 `um` 为单位：

```text
period_x             = 0.60
air_height           = 0.85
substrate_thickness  = 0.35
grating_width        = 0.30
grating_height       = 0.18
pml_top_thickness    = 0.30
pml_bottom_thickness = 0.30
```

这些值对应纳米级结构，例如 `0.30 um = 300 nm`。

## 材料

当前默认材料为：

```text
n_air       = 1.0
n_substrate = 1.45
n_grating   = 1.45
```

相对介电常数使用：

```text
epsilon_r = n^2
```

如果以后要模拟 Si、SiO2、金属或 EUV 材料，只需要在 `src/common/config.py` 中修改折射率，或把 `materials.py` 扩展为复数色散材料。

## 方程

求解散射场形式的频域 Maxwell 方程：

```text
curl(curl(E_scat)) - k0^2 epsilon_r E_scat
  = k0^2 (epsilon_r - epsilon_air) E_inc
```

总场为：

```text
E_total = E_inc + E_scat
```

采用时间因子：

```text
physical field = Re{E exp(-i omega t)}
```

代码使用 `ufl.inner(a, v)`，测试函数在第二个参数位置，符合复数弱式中的共轭约定。

## 有限元空间

主未知量使用一阶 Nedelec 第一类边单元：

```python
element("N1curl", msh.basix_cell(), 1)
```

这保证电场切向分量的有限元连续性，符合 Maxwell curl-curl 问题的自然函数空间 `H(curl)`。

## PML

上下 PML 使用 y 方向复坐标拉伸，但两者的背景材料不同：

- 顶部 PML 是空气区域向上的复坐标延拓；
- 底部 PML 是基座区域向下的复坐标延拓。

这点很重要。如果底部 PML 仍按空气材料处理，就等价于在基座下表面人为放入一个“基座-空气”界面，会产生不应有的反射和散射场突变。

当前 PML 使用官方 DOLFINx PML demo 的复坐标映射。先把 y 坐标平移到物理区域中心：

```text
eta = y - y_center
```

再使用：

```text
eta' = eta + i * alpha / k0 * eta * (|eta| - l_dom/2) / (l_pml/2 - l_dom/2)^2
```

最后得到：

```text
y' = y_center + eta'
```

PML 张量用变换光学公式：

```text
epsilon_pml = det(J) A epsilon A^T
mu_pml      = det(J) A mu A^T
A = J^{-1}
```

其中顶部 PML 的 `epsilon` 取 `epsilon_air`，底部 PML 的 `epsilon` 取 `epsilon_substrate`。

## Floquet 约束

理论边界条件为：

```text
E_right = exp(i kx period_x) E_left
```

由于 Nedelec 自由度是边上的切向积分，自由度符号会受边方向影响。因此程序先构造探针场：

```text
E_probe = (0, exp(i kx x))
```

再用：

```text
scale = dof_right(E_probe) / dof_left(E_probe)
```

得到同时包含 Bloch 相位和 Nedelec 边方向符号的复系数。

## 两个后端

### 官方 `dolfinx_mpc` 后端

文件：

```text
src/runners/run_grating_mpc_official.py
```

实现位置：

```text
src/solvers/solve_vector_maxwell.py::_solve_mpc
```

步骤：

1. 创建 `dolfinx_mpc.MultiPointConstraint(V)`；
2. 把 `slave_dofs`、`master_dofs`、`scales` 传给 `mpc.add_constraint(...)`；
3. 调用 `mpc.finalize()`；
4. 用 `dolfinx_mpc.LinearProblem` 装配带约束系统；
5. PETSc LU 求解；
6. `dolfinx_mpc` 自动回代 slave 自由度。

### 手写矩阵消元后端

文件：

```text
src/runners/run_grating_manual.py
```

实现位置：

```text
src/constraints/floquet_constraint.py::solve_with_constraints
```

步骤：

1. DOLFINx/PETSc 装配完整 `A` 和 `b`；
2. 构造约束矩阵 `C`；
3. 解 reduced system：

```text
C^H A C q = C^H b
```

4. 恢复完整向量：

```text
u = C q
```

## 官方自动周期 helper 的实测限制

我实际尝试了：

```python
mpc.create_periodic_constraint_topological(...)
```

但当前 `dolfinx_mpc v0.10.5` 对 `N1curl` 这种 vector-valued / H(curl) 空间报错：

```text
Periodic conditions for vector valued spaces are not implemented
```

因此本项目没有把它作为正式版本。正式的官方版本使用 `dolfinx_mpc` 的低层约束接口，它仍然由官方库完成约束矩阵装配、求解和回代；手写版本则完全自行处理矩阵约束。

## 本次运行结果

两个版本均已在 Docker 镜像 `code-dolfinx-mpc:latest` 中运行。

通用设置：

```text
PETSc ScalarType = numpy.complex128
mesh cells       = 3504
N1curl dofs      = 5353
Floquet pairs    = 73
dot(k, p)        = 4.441e-16
```

对比结果：

```text
official max(|E_total|) = 1.4761326393531218
manual   max(|E_total|) = 1.4761326393531238

official max(|E_scat|) = 1.5742316028228602
manual   max(|E_scat|) = 1.5742316028228267

official Floquet mismatch = 2.299e-15
manual   Floquet mismatch = 2.277e-15
```

差异：

```text
max_abs_E_total_difference = 1.998e-15
max_abs_E_scat_difference  = 3.353e-14
```

这个差异接近双精度线性代数舍入误差，可以作为两个版本互相印证的证据。

## 2026-06-09 新增实现记录

本次在不删除旧散射场功能的基础上，又加入了端口总场法。

旧散射场法仍然在：

```text
src/solvers/solve_vector_maxwell.py
```

新增端口总场法在：

```text
src/solvers/solve_port_maxwell.py
```

两者共用：

```text
config.py
mesh_builder.py
materials.py
floquet_constraint.py
postprocess.py
```

端口法的核心弱式是：

```text
∫_Ω curl(E) curl(v*) dΩ
- ∫_Ω k0^2 epsilon_r E·v* dΩ
+ ∫_Γtop q_top E_x v_x* ds
+ ∫_Γbottom q_bottom E_x v_x* ds
= -∫_Γtop source_top v_x* ds
```

这里 `E` 就是总场 `E_total`。上边界右端项来自入射端口，底边界没有入射项，只允许出射。`port_boundary_model="robin"` 时，当前实现的是单个 Floquet 基模端口。

同一文件中也已经加入可选的 Fourier 多级次端口。命令行写：

```text
--port-order-count N
```

会临时覆盖 `config.py` 里的 `port_dtn_order_count`。更推荐直接在 `config.py` 中设置：

```python
port_boundary_model = "dtn"
port_dtn_order_count = N
```

这会把端口切向场按：

```text
E_x(x) = sum_m E_m exp(i alpha_m x)
alpha_m = kx + 2*pi*m/period_x
```

展开，并对 `m=-N...N` 逐项加入端口算子。这个算子是非局部的，所以目前放在手写矩阵后端：

```text
--constraint-backend manual
```

当前代码层面的运行选择已经集中到 `SimulationConfig`：

```python
calculation_method
constraint_backend
port_boundary_model
port_dtn_order_count
unique_output
```

`run_cases.py` 会先读取这些 config 默认值；命令行参数只作为临时覆盖。这样在 PyCharm 中直接运行时，也能按照 config 自动生成对应结果目录。

结果目录也已经改成默认唯一目录。当前 v2 每次会写到短路径：

```text
results/2D_grating_..._YYYYMMDD_HHMMSS/
```

如果只运行一个 case，场文件、R/T 文件和 `run_summary.json` 直接放在该目录下；如果一次运行多个 case，才会建立短子目录。若想恢复旧的固定目录，可以加：

```text
--no-unique-output
```

## 2026-06-09 反射率/透射率实现记录

新增：

```text
src/postprocessing/power_metrics.py
```

主要函数：

```text
compute_power_metrics
```

计算流程：

```text
1. 在上方空气均匀区和下方基座均匀区各取一条水平探针线
2. 对 E_total 的 Ex 做 Floquet Fourier 投影
3. 减去已知入射 m=0 分量，得到反射级次
4. 用下方投影得到透射级次
5. 根据每个级次的 beta_m 判断传播/倏逝
6. 对传播级次计算 R_m/T_m，并求和得到 R_total/T_total
```

输出：

```text
power_metrics.json
diffraction_orders.csv
diffraction_orders.json
```

这些指标也会进入每个 case 的 `run_summary.json`，并由 `run_cases.py` 汇总到总目录的 `backend_comparison.json`。同一物理方法的 official/manual 后端会额外比较：

```text
R_total_difference
T_total_difference
R_plus_T_difference
```

### 2026-06-09 晚些时候的修正：从 `Ex` 投影升级为 `Ex+Hz` 功率投影

用户指出无吸收材料下 `R_total + T_total` 不应明显小于 1。检查后确认，旧版后处理只用 `Ex` 做 Floquet 投影，不能严格区分向上波和向下波，因此不适合作为最终能量守恒判断。

现在 `src/postprocessing/power_metrics.py` 已改为：

```text
1. 在上下均匀区域采样 E_total=(Ex,Ey)
2. 用 UFL 写出 curl_z(E)=dEy/dx-dEx/dy
3. 把 Hz_scaled=curl_z(E)/i 插值到 DG 空间
4. 对 Ex 和 Hz_scaled 同时做 Floquet 投影
5. 用 Y_m=(k0 n)^2/beta_m 拆分 Ex_down 和 Ex_up
6. 顶部 Ex_up 统计反射，底部 Ex_down 统计透射
7. 额外输出直接 Poynting 通量诊断
```

核心公式为：

```text
Ex_down = 1/2 (Ex_m + Hz_m / Y_m)
Ex_up   = 1/2 (Ex_m - Hz_m / Y_m)
P_m     = period * 1/2 * Re(Y_m) * |Ex_m|^2
```

新增诊断字段包括：

```text
poynting_R_plus_T_from_net_flux
poynting_energy_residual
top_flux_y_weighted
bottom_flux_y_weighted
top_down_minus_incident_abs
bottom_up_Ex_abs
```

这些字段用于判断 `R+T` 偏差来自物理求解、边界条件、网格导数误差，还是来自衍射级次统计不足。

## 2026-06-09 PML 复坐标公式更新记录

根据用户要求，`src/common/pml.py` 中的 PML 从旧版简化拉伸：

```text
s_y = 1 + i alpha d^2
```

改为官方 DOLFINx PML demo 使用的复坐标映射：

```text
x' = x + i * alpha / k0 * x * (|x| - l_dom/2) / (l_pml/2 - l_dom/2)^2
```

由于本项目的 PML 只在上下方向，所以代码把它作用在 y 方向。又因为物理区域不是关于 `y=0` 对称，代码先定义：

```text
eta = y - y_center
```

再对 `eta` 使用官方公式，最后平移回 `y' = y_center + eta'`。

代码层面新增/修改的函数为：

```text
_pml_coordinate
_y_pml_coordinate
_pml_tensors_from_coordinate_map
top_pml_tensors
bottom_pml_tensors
```

PML 材料张量仍然按坐标变换的 Jacobian 生成：

```text
epsilon_pml = det(J) * inv(J) * epsilon_background * inv(J)^T
mu_pml      = det(J) * inv(J) * mu_background      * inv(J)^T
```

顶部 PML 继续使用空气延拓，底部 PML 继续使用基座延拓。详细说明见：

```text
pml_complex_coordinate_update.md
```
# v2 并行实现补充

v2 在不修改旧版目录的前提下新增了并行铺垫。主要实现点如下：

- `mesh_builder.py` 的 `mesh.xdmf` 写入改为所有 MPI rank 共同进入 `XDMFFile`，避免 HDF5 集合通信不匹配；
- `floquet_constraint.py` 的并行分支不再假设每个 rank 都能看到完整左右边界；
- MPI 下先收集全局 Floquet facet 的 y-key，再让所有 rank 按相同顺序调用 `locate_dofs_topological` 和探针插值；
- `dolfinx_mpc.add_constraint` 使用 master 的全局自由度编号和 owner rank；
- MPI 下 `postprocess.py` 写出 VTX `.bp` 文件，同时写出 `fields_for_paraview_parallel.pvd` 和各 rank 的 `.vtu` 分片；
- MPI 下 `power_metrics.py` 已补充分布式探针线采样，能够直接输出 `power_metrics.json`、`diffraction_orders.csv/json`。

当前已验证：散射场法 `mpc_official` 支持 2 进程 MPI，一阶和二阶 Nedelec 都已跑通；端口总场法 Robin 端口也已用 2 进程 MPI 跑通。并行小网格冒烟测试已确认 `.pvd + rank*.vtu` 和 R/T 文件可以生成。DtN Fourier 端口仍保留串行。
