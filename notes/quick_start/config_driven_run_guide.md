## 2026-06-16 更新：DtN explicit / auxiliary 与自动衍射级

现在 TM 的 Fourier-DtN 端口有两种装配后端：

```python
port_dtn_assembly: str = "auxiliary"
```

这是新的默认推荐值。它给每个端口 Floquet 模态增加一个辅助未知量 `a_m`，避免直接构造端口边界自由度之间的密集外积块，更适合以后扩展到 3D。

```python
port_dtn_assembly: str = "explicit"
```

这是旧的显式外积法，会直接形成类似 `Q^*YQ` 的端口矩阵。它保留作为 reference/debug，用来和 auxiliary 对照。

PyCharm 中直接改 `src/main.py`：

```python
PORT_BOUNDARY_MODEL = "dtn"
PORT_DTN_ASSEMBLY = "auxiliary"   # auxiliary / explicit
```

衍射级选择也新增了一个更直观的开关：

```python
PORT_USE_DIFFRACTION_ORDERS = False
```

只使用 0 级：

```text
top = [0]
bottom = [0]
```

```python
PORT_USE_DIFFRACTION_ORDERS = True
```

程序会根据：

```text
|kx + 2*pi*m/L| < n_j*k0
```

分别自动判断上端口空气侧和下端口基座侧有哪些明确传播级次。0 级始终保留。如果某个级次接近 Rayleigh anomaly，程序会在日志和 `run_summary.json` 中记录 warning 信息。

运行后结果文件夹名称也会反映设置，例如：

```text
2D_grating_tm_port_ptdtn_dtn0_aux_...
2D_grating_tm_port_ptdtn_dtnauto_aux_...
2D_grating_tm_port_ptdtn_dtn0_exp_...
```

其中：

```text
dtn0      只使用 0 级
dtnauto   自动传播衍射级
aux       auxiliary 辅助变量法
exp       explicit 显式外积法
```

如果使用 auxiliary，会额外输出：

```text
dtn_auxiliary_amplitudes.json
dtn_auxiliary_power_metrics.json
dtn_auxiliary_diffraction_orders.csv
```

和 COMSOL Periodic Port 对比时，DtN 结果优先看：

```text
dtn_port_power_metrics.json
dtn_auxiliary_power_metrics.json
```

两者理论上应基本一致。`power_metrics.json` 的水平探测线法仍然保留，但它更适合作为内部场诊断。

## 2026-06-15 更新：偏振、复折射率和端口 PML

现在 `src/main.py` 多了一个最常用的新开关：

```python
POLARIZATION_TYPE = "TM"  # 原来的 Ex/Ey 矢量 Maxwell
POLARIZATION_TYPE = "TE"  # 新增的 Ez 标量 Maxwell
```

命令行等价写法是：

```bash
--polarization-type TM
--polarization-type TE
```

复数折射率在 `src/common/config.py` 中直接改：

```python
n_air = 1.0 + 0.0j
n_substrate = 1.45 + 0.0j
n_grating = 1.45 + 0.02j
```

程序会自动使用：

```text
epsilon_r = n^2
```

如果 `n_grating` 有正虚部，后处理会在 `power_metrics.json` 或 `dtn_port_power_metrics.json` 里输出：

```text
A_balance
A_volume
absorption_difference_volume_minus_balance
```

注意：端口总场法当前禁止：

```python
PORT_USE_PML = True
```

原因是端口法的弱式已经把上下边界当成 Robin/DtN 端口；如果再生成 PML 网格，而端口弱式又没有把 PML 单元加入 Maxwell/PML 体积分，就会让 PML 内自由度没有正确约束。因此程序会在运行开始阶段直接报错，避免生成不可信结果。

# 通过 main.py 选择算例和端口模型

本文说明当前推荐的 PyCharm 运行方式：优先修改 `src/main.py` 文件开头的大写变量，然后直接运行 `src/main.py`。`src/main.py` 会调用 `src/runners/run_cases.py`，真正求解器仍在 `src/solvers/` 里。命令行参数和 `src/common/config.py` 仍然保留，但主要作为临时覆盖和默认参数来源。

## 1. 为什么要改成配置驱动

以前很多选择写在命令行里，例如：

```text
--formulation port_total
--scattering-background layered
--port-order-count 1
```

这样容易忘，也不适合在 PyCharm 里反复点 Run。现在 PyCharm 日常运行时优先看：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/src/main.py
```

里面最重要的是：

```python
CALCULATION_METHOD = "scattered"
CONSTRAINT_BACKEND = "mpc_official"
SCATTERING_BACKGROUND = "layered"
PORT_BOUNDARY_MODEL = "robin"
COMPUTE_POWER_METRICS = True
```

如果 `NEDELEC_DEGREE`、`MESH_TARGET_SIZE`、`INCIDENT_ANGLE_DEG` 等变量写成 `None`，程序会继续使用下面这个配置文件中的默认值：

```text
fenics_vector_maxwell_floquet_demo_v2_parallel/src/common/config.py
```

最重要的是下面这些变量：

```python
calculation_method: str = "all"
constraint_backend: str = "both"
port_boundary_model: str = "all"
scattering_background: str = "layered"
port_dtn_order_count: int = 1
port_use_pml: bool = False
unique_output: bool = True
```

## 2. calculation_method：选择物理方法

```python
calculation_method: str = "scattered"
```

只运行散射场法：

```text
E_total = E_background + E_scat
```

```python
calculation_method: str = "port"
```

只运行端口总场法：

```text
直接求 E_total
```

```python
calculation_method: str = "all"
```

同时运行散射场法和端口总场法。

## 3. scattering_background：散射场法的背景

这个变量只对 `calculation_method="scattered"` 有意义。

```python
scattering_background: str = "air"
```

表示旧版全空气背景。基座也会被当作相对空气的散射源。

```python
scattering_background: str = "layered"
```

表示新版平坦空气/基座背景。平坦基座属于背景，主要让光栅凸起成为散射源。

## 4. port_boundary_model：端口法边界模型

这个变量只对 `calculation_method="port"` 或 `"all"` 中的端口法有意义。

```python
port_boundary_model: str = "robin"
```

运行当前的局部 Robin 端口。它只包含 Floquet 基模 `m=0`，可以用 official MPC 和手写矩阵两个后端互相验证。

```python
port_boundary_model: str = "dtn"
```

运行 Fourier 模态 DtN 周期端口。它把端口截面展开成多个 Floquet 衍射级次，更接近 COMSOL 的 Periodic Port。当前 DtN 是非局部矩阵算子，所以只使用 `manual` 后端。

```python
port_boundary_model: str = "all"
```

同时运行 Robin 端口和 DtN 端口。

## 5. port_dtn_order_count：DtN 保留几个衍射级次

```python
port_dtn_order_count: int = 1
```

表示保留：

```text
m = -1, 0, +1
```

更一般地：

```text
port_dtn_order_count = N
```

表示保留：

```text
m = -N, ..., -1, 0, 1, ..., N
```

要和 COMSOL 对比时，这个数字应尽量和 COMSOL 周期端口里的 diffraction orders 设置一致。若 COMSOL 只启用基模，`N=0` 即可；若 COMSOL 包含 `-1,0,+1`，这里就设为 `1`。

## 6. constraint_backend：选择 Floquet 约束后端

```python
constraint_backend: str = "mpc_official"
```

只用官方 `dolfinx_mpc` 低层约束接口。

```python
constraint_backend: str = "manual"
```

只用手写矩阵消元：

```text
u = C q
C^H A C q = C^H b
```

```python
constraint_backend: str = "both"
```

同一种物理方法下，official 和 manual 都跑一遍，用来互相验证。

注意：`port_boundary_model="dtn"` 时，即使 `constraint_backend="both"`，DtN 端口也只会运行 manual 后端，因为 DtN 端口是非局部矩阵算子。

## 7. unique_output：每次生成新结果目录

```python
unique_output: bool = True
```

每次运行都会生成类似：

```text
results/2D_grating_all_lay_ptall_dtn1_p2_h25p0_t85p0_YYYYMMDD_HHMMSS/
```

文件夹名字会反映本次选择：

```text
all                 同时跑 scattered 和 port
lay                 散射场背景为 layered
ptall               端口法同时跑 robin 和 dtn
dtn1                DtN 保留 m=-1,0,+1
p2                  二阶 Nedelec 边元
h25p0               mesh_target_size = 25.0
t85p0               incident_angle_deg = 85.0
```

如果本次只运行一个 case，结果文件会直接写在这个 `2D_grating_*` 目录中。只有一次运行多个 case 时，才会在里面建立 `sc_lay_mpc/`、`port_robin_mpc/` 这类短子目录。

里面的子文件夹也会继续反映具体算例：

```text
air_substrate_grating_scattered_layered_mpc_official
air_substrate_grating_scattered_layered_manual
air_substrate_grating_port_robin_mpc_official
air_substrate_grating_port_robin_manual
air_substrate_grating_port_dtn_orders1_manual
```

如果设为：

```python
unique_output: bool = False
```

则恢复旧的固定目录写法，不推荐反复对比时使用。

## 8. 推荐配置

如果你想一次比较所有主要版本：

```python
calculation_method = "all"
constraint_backend = "both"
scattering_background = "layered"
port_boundary_model = "all"
port_dtn_order_count = 1
unique_output = True
```

这会生成五个结果：

```text
scattered layered + official MPC
scattered layered + manual
port robin + official MPC
port robin + manual
port dtn + manual
```

如果你只想和 COMSOL 周期端口对比：

```python
calculation_method = "port"
constraint_backend = "manual"
port_boundary_model = "dtn"
port_dtn_order_count = 1
unique_output = True
```

这时重点看 ParaView 中的：

```text
E_total_abs
E_total_Ex_real / E_total_Ex_imag
E_total_Ey_real / E_total_Ey_imag
domain_tag
material_id
```

## 9. DtN 和 COMSOL 的关系

COMSOL 的周期端口本质上会做 Floquet 模态展开。当前 FEniCS DtN 端口也按这个思路做：

```text
E_x(x) = sum_m E_m exp(i alpha_m x)
alpha_m = kx + 2*pi*m/period_x
```

每个模态的竖向波数为：

```text
beta_m = sqrt((k0 n)^2 - alpha_m^2)
```

端口对每个模态施加出射关系：

```text
q_m = -i (k0 n)^2 / beta_m
```

在 `port_dtn_order_count` 和 COMSOL 的 diffraction orders 一致时，这个边界模型就是更接近 COMSOL Periodic Port 的版本。实际数值仍会受到网格、单元阶次、COMSOL 端口归一化、材料参数和后处理插值方式影响，所以建议先比较 `E_total_abs`，再比较分量和功率。

## 10. 反射率和透射率后处理

默认：

```python
compute_power_metrics = True
diffraction_order_count = 1
```

每个算例都会输出：

```text
power_metrics.json
diffraction_orders.csv
diffraction_orders.json
```

其中：

```text
R_total                 总反射率
T_total                 总透射率
R_plus_T                能量守恒检查
R_order / T_order       每个 Floquet 衍射级次的反射率/透射率
reflected_Ex_phase      反射级次相位
transmitted_Ex_phase    透射级次相位
```

如果 COMSOL 中只统计 `m=-1,0,+1`，这里就设：

```python
diffraction_order_count = 1
```

详细理论见：

```text
../theory/reflection_transmission_metrics.md
```

2026-06-09 更新：新版 R/T 后处理已经改成 `Ex + Hz` 的 Poynting 模态分解版本。代码会从

```text
Hz_scaled = (dEy/dx - dEx/dy) / i
```

恢复缩放磁场，再把每个 Floquet 级次拆成向上波和向下波。因此新增或重点推荐查看：

```text
poynting_R_plus_T_from_net_flux
poynting_energy_residual
top_down_minus_incident_abs
bottom_up_Ex_abs
```

使用 DtN 端口和 COMSOL 周期端口对比时，建议同时设置：

```python
port_dtn_order_count = 1
diffraction_order_count = 1
```

前者决定端口边界条件保留多少个 Floquet 级次，后者决定后处理统计多少个反射/透射级次。二者最好和 COMSOL 的 diffraction orders 一致。

# v2 运行提示

v2 的串行运行方式和旧版基本一致，但 MPI 下有一个重要规则：

```text
manual 后端和 DtN Fourier 端口仍是串行功能；
MPI 下请优先使用 constraint_backend="mpc_official"；
MPI 下 port_boundary_model="all" 会自动收缩为 Robin 端口。
```

推荐的 MPI 命令是：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation scattered \
  --constraint-backend mpc_official \
  --scattering-background layered
```

或者：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main \
  --formulation port \
  --constraint-backend mpc_official \
  --port-boundary-model robin
```
