# 周期端口总场法、唯一结果目录与代码更新说明

本文记录 2026-06-09 新增的功能。新增内容是在原有散射场方法之外，再补充一种更接近 COMSOL 周期端口思路的总场端口法。

## 1. 本次新增功能概览

现在代码里有两类计算方法。

第一类是原来的散射场法：

```text
E_total = E_background + E_scat
```

它通过等效背景场产生右端源项，求解散射场 `E_scat`。这部分功能保留不变。

第二类是新加的端口总场法：

```text
直接求 E_total
```

它不再用体源项模拟入射，而是在上边界端口施加入射波，在下边界端口施加出射边界。左右边界仍然使用 Floquet 准周期条件。

此外，本次还新增了唯一结果目录功能。默认每次运行都会生成一个新的：

```text
results/run_..._YYYYMMDD_HHMMSS
```

这样旧结果不会被覆盖。

## 2. 和旧功能的关系

本次没有删除旧功能。

旧功能入口仍然是：

```powershell
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation scattered
```

如果不写 `--formulation`，默认也是：

```text
scattered
```

新增端口法入口是：

```powershell
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation port_total
```

如果想同一组里同时跑旧散射场法和新端口法：

```powershell
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation both
```

## 3. 端口总场法的物理图像

COMSOL 周期端口的常见思路是：

```text
上端口：给定一个入射 Floquet 模
下端口：允许向下出射的透射模离开
左右边界：Floquet 周期条件
内部：求总电场 E_total
```

新增的 `port_total` 方法就是按这个思路写的。

当前实现的端口模型是：

```text
single Floquet fundamental mode Robin port
```

也就是 Floquet 基模端口。它和 COMSOL 的端口方向是一致的。若 COMSOL 自动包含多个传播衍射级次，可以使用本文后面新增的 `--port-order-count N` 多级次 Fourier 端口。

## 4. 总场强形式

端口法直接求总场：

```text
E = E_total
```

物理区域中频域 Maxwell 方程是：

```text
curl curl(E) - k0^2 epsilon_r E = 0
```

这里：

```text
k0 = 2 pi / lambda0
epsilon_r = n^2
```

本项目是二维截面，电场只取平面内分量：

```text
E = (Ex, Ey, 0)
```

所以：

```text
curl(E) = (0, 0, dEy/dx - dEx/dy)
```

代码中 `curl_3d(field)` 就是把二维平面内电场转成这个三维 curl 表达。

## 5. 为什么端口法不需要体源项

散射场法里有右端项：

```text
k0^2 (epsilon_actual - epsilon_background) E_background
```

这是因为散射场法把入射场藏在背景场里。

端口总场法不是这样。它直接求总场，并在边界上注入入射波，所以体内没有这个背景散射源。端口总场法的体方程就是齐次的：

```text
curl curl(E) - k0^2 epsilon_r E = 0
```

入射信息通过上端口边界条件进入系统。

## 6. 水平端口上的模式关系

对一个横向波数为 `kx` 的 Floquet 基模，空气中的波数是：

```text
k_air = k0 n_air
```

竖向波数是：

```text
beta_air = sqrt(k_air^2 - kx^2)
```

基座中的波数是：

```text
k_sub = k0 n_substrate
beta_sub = sqrt(k_sub^2 - kx^2)
```

代码使用 `_positive_sqrt()` 选择物理正确的平方根，避免选到增长的倏逝波或错误传播方向。

向下传播的入射波写成：

```text
E_inc = A p exp(i(kx x - beta_air y))
```

在代码里：

```text
ky = -beta_air
E_inc = A p exp(i(kx x + ky y))
```

其中 `A = port_incident_amplitude`，默认是 1。

## 7. 端口 Robin 条件的直观解释

端口边界要做到两件事：

```text
1. 上端口注入已知入射波
2. 上端口和下端口都允许出射波离开，不把它们反射回来
```

对水平边界来说，切向电场主要是 `Ex`。对于一个出射 Floquet 模，可以写成：

```text
boundary_curl_term = q Ex
```

其中：

```text
q = -i k^2 / beta
```

上端口在空气中，所以：

```text
q_top = -i k_air^2 / beta_air
```

下端口在基座中，所以：

```text
q_bottom = -i k_sub^2 / beta_sub
```

这个 `q` 就是一个一阶模式阻抗/导纳关系。它告诉边界：如果你看到某个切向电场，就让它以对应的 Floquet 出射模离开。

## 8. 上端口入射项如何进入右端

上端口总场可以分成：

```text
E_total = E_inc + E_out
```

边界算子对出射波满足：

```text
B(E_out) = q_top E_out_x
```

但总场里还包含已知入射波，所以：

```text
B(E_total)
= B(E_inc) + B(E_out)
```

又因为：

```text
E_out_x = E_total_x - E_inc_x
```

所以：

```text
B(E_total)
= q_top E_total_x + [B(E_inc) - q_top E_inc_x]
```

对向下入射的基模：

```text
B(E_inc) = +i k_air^2 / beta_air * E_inc_x
```

因此上端口源项是：

```text
top_source
= (i k_air^2 / beta_air - q_top) E_inc_x
= 2 i k_air^2 / beta_air E_inc_x
```

代码中对应：

```python
top_source = 2j * k_air**2 / beta_air * incident_x
```

## 9. 端口法弱形式

体内强形式：

```text
curl curl(E) - k0^2 epsilon_r E = 0
```

乘测试函数 `v` 并积分，得到体积分：

```text
integral curl(E) · conj(curl(v)) dOmega
- k0^2 integral epsilon_r E · conj(v) dOmega
```

端口边界贡献加入左端：

```text
integral_top q_top Ex conj(vx) ds
+ integral_bottom q_bottom Ex conj(vx) ds
```

上端口入射波进入右端：

```text
- integral_top top_source conj(vx) ds
```

因此代码里的弱式是：

```python
a = (
    inner(curl_3d(u), curl_3d(v)) * d_physical
    - k0**2 * eps * inner(u, v) * d_physical
    + inner(q_top * u[0], v[0]) * ds(outer_top)
    + inner(q_bottom * u[0], v[0]) * ds(outer_bottom)
)

L = -inner(top_source, v[0]) * ds(outer_top)
```

这里 `u` 是未知总场 `E_total`，不是散射场。

## 10. 为什么端口法默认不使用 PML

端口边界本身就是出射边界，所以第二种方法默认：

```text
use_pml = False
```

也就是说网格只包含物理区域：

```text
空气 + 光栅 + 基座
```

上边界就是上端口，下边界就是下端口。

如果你想保留 PML 层，也可以运行：

```powershell
--port-use-pml
```

但要注意：这时端口位于 PML 外边界，和 COMSOL 的端口位置是否一致需要你在模型里一起确认。默认无 PML 更容易理解，也更像“端口直接截断物理区域”。

## 11. 与 COMSOL 周期端口的关系

当前新增端口法已经具备这些 COMSOL 周期端口特征：

```text
上端口注入 Floquet 入射基模
下端口吸收向下传播的基模
左右边界使用 Floquet 准周期条件
直接求总电场 E_total
```

仍需注意的差别：

```text
COMSOL 周期端口可能自动包含多个衍射级次
当前代码先实现单个 Floquet 基模 Robin 端口
```

如果周期、波长和入射角使多个衍射级次可传播，那么要做到更严格的 COMSOL 一致，应使用后文的 Fourier 模态端口，把端口边界从本地 Robin 条件升级成非局部 DtN 条件：

```text
Ex(x) = sum_m a_m exp(i(kx + 2 pi m / period_x) x)
B(Ex) = sum_m q_m a_m exp(i(kx + 2 pi m / period_x) x)
```

其中：

```text
q_m = -i k^2 / beta_m
beta_m = sqrt(k^2 - (kx + 2 pi m / period_x)^2)
```

这就是后续要进一步逼近 COMSOL 的方向。

## 12. 新增结果目录机制

以前结果直接写入：

```text
results/air_substrate_grating_manual
results/air_substrate_grating_mpc_official
```

如果目录已经存在，就会覆盖里面的文件。

现在默认写入：

```text
results/run_air_substrate_grating_..._YYYYMMDD_HHMMSS/
```

例如：

```text
results/run_air_substrate_grating_both_layered_20260609_012431/
  air_substrate_grating_layered_manual/
  air_substrate_grating_port_total_manual/
  all_run_summary.json
  backend_comparison.json
```

如果同一秒内已经有同名目录，会自动追加：

```text
_02
_03
...
```

实现位置：

```text
src/common/output_paths.py
```

## 13. 如何恢复旧的固定目录写法

如果你确实希望像以前一样写入固定目录，可以加：

```powershell
--no-unique-output
```

例如：

```powershell
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation scattered --no-unique-output
```

## 14. 常用运行命令

### 14.1 旧散射场法，空气背景

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation scattered --constraint-backend both --scattering-background air"
```

### 14.2 旧散射场法，分层背景

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation scattered --constraint-backend both --scattering-background layered"
```

### 14.3 新端口总场法

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation port_total --constraint-backend both"
```

### 14.4 同一组里同时跑散射场法和端口法

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation both --constraint-backend manual --scattering-background layered"
```

### 14.5 快速排错用粗网格

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation both --constraint-backend manual --scattering-background layered --mesh-target-size 0.08 --visualization-degree 1"
```

## 15. 参数解释

```text
--formulation scattered
```

使用原来的背景场散射法。

```text
--formulation port_total
```

使用新增的端口总场法。

```text
--formulation both
```

在同一个 run 文件夹中同时跑两种方法。

```text
--constraint-backend manual
```

使用手写矩阵约束消元。

```text
--constraint-backend mpc_official
```

使用官方 dolfinx_mpc 低层约束接口。

```text
--constraint-backend both
```

同时跑官方 MPC 和手写矩阵版。

```text
--scattering-background layered
```

只对 `scattered` 方法有意义，表示用平坦空气/基座背景。

```text
--port-use-pml
```

只对 `port_total` 方法有意义，表示保留 PML 层并把端口放在最外边界。

```text
--no-unique-output
```

恢复旧的固定目录输出方式。

## 16. 代码逐行讲解：`solve_port_maxwell.py`

| 行号 | 说明 |
|---|---|
| 1-22 | 导入依赖。这里复用了现有的网格、材料、Floquet 约束和后处理函数。 |
| 25-29 | `_positive_sqrt` 选择物理正确的平方根，用于端口竖向波数 `beta`。 |
| 32-44 | `port_incident_field_function` 构造上端口入射波，也就是 `E_inc = A p exp(i(kx x + ky y))`。 |
| 47-51 | `_subtract_fields` 只用于输出参考散射场：`E_scat_reference = E_total - E_inc`。端口法真正求的是 `E_total`。 |
| 54-56 | `run_port_case` 是端口总场法主函数。 |
| 57-67 | 创建输出目录、日志，检查 complex PETSc。 |
| 69-76 | 打印算例名、端口法标记、是否使用 PML、波数和 Floquet 相位。 |
| 78-87 | 建网格、创建 Nedelec `H(curl)` 空间。 |
| 89 | 创建真实介电常数 `epsilon_r`。 |
| 90 | 创建上端口入射场，用于输出和参考差值。 |
| 91-94 | 创建左右 Floquet 约束并打印检查误差。 |
| 96-101 | 创建 trial/test 函数以及体积分、边界积分 measure。 |
| 103-108 | 计算空气和基座端口的 `k`、`beta`、`q_top`、`q_bottom`。 |
| 110-115 | 计算上端口入射波的 `Ex` 和右端源项 `top_source`。 |
| 117-122 | 组装端口总场法左端弱式。前两项是体内 Maxwell，后两项是上下端口 Robin 条件。 |
| 123 | 组装上端口入射右端项。 |
| 125-128 | 官方 `dolfinx_mpc` 求解路线。 |
| 129-141 | 手写矩阵约束消元路线。 |
| 145-146 | 计算参考散射场并保存 ParaView/PNG 输出。 |
| 147-148 | 计算 Floquet mismatch 和耗时。 |
| 150-173 | 写入 `run_summary.json` 的核心字段。 |
| 174-179 | 打印关键结果。 |
| 181-188 | 保存 `run_summary.json` 和 `solver_log.txt`。 |

## 17. 代码逐行讲解：`src/runners/run_cases.py` 新入口

| 行号 | 说明 |
|---|---|
| 1-12 | 导入命令行工具、配置、唯一目录工具、散射场求解器和端口求解器。 |
| 15-16 | `_backend_list` 把 `both` 展开为 `mpc_official` 和 `manual`。 |
| 19-20 | `_case_name` 拼接输出目录名。 |
| 23-31 | `_base_updates` 读取阶次、可视化阶次和网格尺寸参数。 |
| 34-67 | 定义命令行参数，包括新增的 `--formulation`、`--port-use-pml`、`--no-unique-output`。 |
| 69-70 | 防止端口法误用官方自动 periodic helper。 |
| 72-85 | 创建本次运行的唯一 run 目录。 |
| 87-126 | 按 formulation 和 backend 循环运行算例。 |
| 94-110 | 运行旧散射场法。 |
| 111-126 | 运行新端口总场法。 |
| 128-153 | 写出一组运行的 `all_run_summary.json` 和 `backend_comparison.json`。 |

## 18. 代码逐行讲解：`mesh_builder.py` 的 PML 开关

| 行号 | 说明 |
|---|---|
| 29-36 | y 坐标现在根据 `cfg.use_pml` 决定是否包含上下 PML 层。 |
| 81-84 | 只有 `use_pml=True` 时才把最上/最下层标记为 PML。 |
| 105-107 | 只有某个材料区域确实有 surface 时才创建 PhysicalGroup，避免无 PML 时创建空 PML 组。 |
| 121-131 | 无论是否有 PML，最上和最下边界都会标记为 `outer_top`、`outer_bottom`，供端口边界使用。 |

## 19. 代码逐行讲解：`output_paths.py`

| 行号 | 说明 |
|---|---|
| 1-4 | 导入时间和路径工具。 |
| 7 | `unique_run_dir` 根据基础名字生成唯一结果目录。 |
| 8-9 | 如果关闭唯一目录，就返回原结果根目录。 |
| 11-14 | 使用当前时间生成目录名。 |
| 16-21 | 如果同一秒内重名，就自动追加 `_02`、`_03`。 |

## 20. 本次实际验证

已在 Docker 中运行：

```text
port_total + manual
port_total + mpc_official
scattered + layered + manual
formulation both + manual
```

关键现象：

```text
新增结果目录成功生成 run_* 文件夹
端口法 use_pml=False 的无 PML 网格成功生成
Floquet 探针重构误差约 1e-15
端口法 total field 求解成功
ParaView 文件 fields_for_paraview.vtu 成功输出
```

示例结果目录：

```text
results/run_air_substrate_grating_port_total_20260609_012011
results/run_air_substrate_grating_both_layered_20260609_012431
results/run_air_substrate_grating_port_total_20260609_012821
```

## 21. 当前推荐工作流

如果要和 COMSOL 对比，建议按下面顺序：

```text
1. 先用 --formulation port_total --constraint-backend manual 快速跑通
2. 在 ParaView 中比较 E_total_abs
3. 再用 --constraint-backend both 检查官方 MPC 和手写矩阵版一致性
4. 如果和 COMSOL 仍有明显差异，检查 COMSOL 是否启用了多个衍射级次端口
5. 若启用多级次，使用 --port-order-count N，并让 N 对齐 COMSOL 的 diffraction orders
```

对于旧散射场法：

```text
scattered + layered 仍然适合做背景场散射解释
port_total 更适合对照 COMSOL 的端口激励图
```

## 22. 老入口脚本的结果目录也已更新

除了 `run_cases.py`，两个单独入口脚本也已经改成每次生成唯一结果目录：

```text
src/runners/run_grating_manual.py
src/runners/run_grating_mpc_official.py
```

它们的物理功能没有改变：

```text
run_grating_manual.py        只运行手写矩阵 Floquet 约束版
run_grating_mpc_official.py  只运行官方 dolfinx_mpc 约束版
```

改变的只是输出位置。以前会写到固定目录，现在会写到类似：

```text
results/air_substrate_grating_manual_YYYYMMDD_HHMMSS/
results/air_substrate_grating_mpc_official_YYYYMMDD_HHMMSS/
```

这样即使你在 PyCharm 里反复点击 Run，也不会把上一轮图片和 `fields_for_paraview.vtu` 覆盖掉。

## 23. 多衍射级次 Fourier 周期端口

上面的端口 Robin 条件只包含 Floquet 基模，也就是 `m=0`。COMSOL 的周期端口通常会把端口截面上的场分解成多个 Floquet 衍射级次，所以这里又补充了一个更接近 COMSOL 的可选功能：

```text
--port-order-count N
```

它表示端口保留：

```text
m = -N, ..., -1, 0, 1, ..., N
```

### 23.1 Floquet 级次怎么写

因为左右边界是 Floquet 周期边界，所以端口上的切向电场 `E_x(x)` 不是普通周期函数，而是带着准周期相位：

```text
E_x(x + period_x) = exp(i kx period_x) E_x(x)
```

这种函数可以展开成：

```text
E_x(x) = sum_m E_m exp(i alpha_m x)
```

其中：

```text
alpha_m = kx + 2*pi*m/period_x
```

`m=0` 是入射基模，`m=-1`、`m=1` 等就是不同衍射级次。

每个级次在某个均匀介质中的竖向波数为：

```text
beta_m = sqrt((k0 n)^2 - alpha_m^2)
```

如果 `beta_m` 是实数，这个级次是传播波；如果 `beta_m` 是纯虚数，这个级次是倏逝波。

### 23.2 每个级次的出射关系

对当前二维 in-plane 电场，端口边界需要的是切向电场 `E_x` 和标量旋度：

```text
curl_z(E) = dEy/dx - dEx/dy
```

对某个 Floquet 级次：

```text
E_x,m exp(i alpha_m x)
```

出射端口关系可以写成：

```text
q_m = -i (k0 n)^2 / beta_m
```

上端口和下端口都使用这个 `q_m`，只是边界弱式中的法向符号已经体现在前面推导的边界项里。

### 23.3 非局部弱式为什么不能直接写成普通 UFL 边界积分

单基模端口可以写成局部形式：

```text
integral q E_x conj(v_x) ds
```

但多级次端口要先把 `E_x` 投影到每个 Fourier 级次，再把结果求和。投影系数为：

```text
E_m = (1/period_x) integral E_x(x) exp(-i alpha_m x) dx
```

所以端口弱式是：

```text
(1/period_x) sum_m q_m
  [integral E_x exp(-i alpha_m x) dx]
  [integral exp(i alpha_m x) conj(v_x) dx]
```

这不是一个点对点的局部积分，而是“一个边界积分乘另一个边界积分”的非局部算子。因此代码中没有把它塞进普通 UFL bilinear form，而是在 PETSc 矩阵装配后手动加矩阵块。

### 23.4 代码里如何做

在 `solve_port_maxwell.py` 中：

```text
_fourier_trace_vector
```

装配每个模态的 trace 向量：

```text
l_j = integral exp(i alpha_m x) conj(phi_j,x) ds
```

这里 `phi_j,x` 是第 `j` 个 Nedelec 基函数在端口上的 x 分量。

然后：

```text
_sparse_outer_trace
```

用外积构造端口矩阵：

```text
A_port[j, i] += (q_m/period_x) l_j conj(l_i)
```

最后：

```text
_add_fourier_port_operators
```

对上、下端口和 `m=-N...N` 全部求和。上端口的 `m=0` 级次还会加入入射源项：

```text
b_j += -source_0 l_j
```

### 23.5 如何运行

包含 `m=-1,0,1` 三个级次：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --formulation port_total --constraint-backend manual --port-order-count 1"
```

包含更多级次时增大数字，例如：

```text
--port-order-count 2
```

表示包含：

```text
m = -2, -1, 0, 1, 2
```

当前多级次 Fourier 端口只支持：

```text
--constraint-backend manual
```

原因是它要手动向矩阵中加入非局部端口块，而官方 `dolfinx_mpc.LinearProblem` 主要处理普通 UFL 局部弱式装配。

### 23.6 本次验证

我已经在 Docker 中运行了粗网格测试：

```text
--formulation port_total
--constraint-backend manual
--mesh-target-size 0.12
--visualization-degree 1
--port-order-count 1
```

结果目录：

```text
results/run_air_substrate_grating_port_total_20260609_014534/
```

关键结果：

```text
port_model = multi-order Fourier Floquet DtN port
port_boundary_model = dtn
port_dtn_order_count = 1
mesh cells = 154
N1curl dofs = 806
reduced residual = 8.955e-15
Floquet mismatch total dof = 0.000e+00
max |E_total| = 1.471686
```

`run_summary.json` 中的 `port_modes` 会列出每个端口、每个级次的：

```text
side
order
alpha
beta
q
num_trace_dofs
```

这就是和 COMSOL 周期端口逐项对照时最有用的检查信息。

## 24. 配置式运行入口

现在推荐优先改 `src/common/config.py`，而不是记命令行参数。端口法相关变量是：

```python
calculation_method = "port"      # 或 "all"
constraint_backend = "manual"    # DtN 端口目前只支持 manual
port_boundary_model = "dtn"      # robin / dtn / all
port_dtn_order_count = 1
port_use_pml = False
unique_output = True
```

如果设为：

```python
calculation_method = "all"
constraint_backend = "both"
port_boundary_model = "all"
```

会生成：

```text
scattered layered + official MPC
scattered layered + manual
port robin + official MPC
port robin + manual
port dtn + manual
```

结果总目录名会包含类似：

```text
run_air_substrate_grating_all_bg_layered_port_all_dtn1_YYYYMMDD_HHMMSS
```

详细操作见：

```text
../quick_start/config_driven_run_guide.md
```

## 25. 端口法中的 R/T 指标

端口法现在会额外输出：

```text
power_metrics.json
diffraction_orders.csv
diffraction_orders.json
```

这组是通用的水平探测线后处理。对 Robin 端口，R/T 是从解出的 `E_total` 在上下均匀层里做 Floquet 投影得到的。对 DtN 端口，这组文件仍然保留，用来和其他方法保持同一种后处理口径。

如果使用 DtN 端口：

```python
port_boundary_model = "dtn"
```

还会多输出一组端口面模态幅值结果：

```text
dtn_port_power_metrics.json
dtn_port_diffraction_orders.csv
dtn_port_diffraction_orders.json
```

这一组直接复用 DtN 端口矩阵装配时的 Fourier 边界积分投影向量。当前代码保存的是压缩后的投影向量，也就是只保存非零自由度编号 `indices` 和对应复数值 `values`，不再保存长度等于全局自由度数的完整 dense `ell`。上端口用“总场级次幅值减去已知入射基模”得到反射幅值，下端口用总场级次幅值得到透射幅值，因此更接近 COMSOL Periodic Port 的 diffraction order power 定义。

另外，DtN 端口矩阵项现在也改成了一次性 COO 稀疏矩阵构造。旧写法是每个级次生成一个稀疏矩阵后反复相加，容易产生额外中间矩阵；新写法是先收集所有级次的 `rows/cols/data`，最后统一构造 `A_port`。这不改变数学公式，只降低多级次端口时的临时内存峰值。

`run_summary.json` 中会同时保存：

```text
power_metrics                         水平探测线法
dtn_port_power_metrics                DtN 端口面法
dtn_port_vs_probe_power_difference    两者的 R/T 差值
```

本次粗网格验证：

```text
port robin:                    R+T 约 0.989875
port dtn 水平探测线，95% 位置:   R+T 约 0.956064
port dtn 边界积分端口法:         R+T 约 1.000000
```

说明在 DtN 端口法中，复用端口边界积分向量得到的模态幅值结果更适合直接与 COMSOL 周期端口对比；水平探测线结果仍然有用，它可以作为内部场分解和采样位置是否稳定的额外诊断。

新增后处理理论见：

```text
reflection_transmission_metrics.md
```
## 2026-06-15 更新：为什么端口法禁止 port_use_pml=True

当前端口总场法把上、下外边界直接当成端口边界，使用 Robin 或 Fourier DtN 条件。因此正常设置是：

```python
port_use_pml = False
```

本次检查发现，如果把端口法强行改成：

```python
port_use_pml = True
```

网格会生成 PML 区域，但端口法弱式中的体积分仍然只包含：

```text
air/substrate/grating
```

也就是：

```text
d_physical = dx((air, substrate, grating))
```

PML 单元不会得到 Maxwell/PML 体积分项，这会让 PML 内自由度缺少物理方程约束。为了避免生成不可信结果，入口层 `run_cases.py` 和求解器层 `solve_port_maxwell.py`、`solve_te_maxwell.py` 都会显式禁止 `port_use_pml=True`。

如果未来确实要实现“端口 + PML”，需要重新推导总场端口法在 PML 区域内的弱式，而不是只打开 PML 网格。
