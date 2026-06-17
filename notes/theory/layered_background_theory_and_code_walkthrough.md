# 分层背景散射模型、弱形式推导与代码逐行讲解

这份文档记录本次为了贴近 COMSOL 周期端口结果而做的代码补充。目标是让没有太多有限元和电磁背景的人，也能顺着公式和代码知道程序到底在算什么。

## 1. 本次到底改了什么

原来的代码没有删除，仍然保留为：

```text
scattering_background = "air"
```

它的含义是：把入射场看成“全空间都是空气时的平面波”。真实材料仍然包含空气、基座和光栅，但散射源是相对于空气背景写出来的。

本次新增了一个更接近 COMSOL 周期端口设置的版本：

```text
scattering_background = "layered"
```

它的含义是：先把“上方空气 + 下方平坦基座”当作背景问题，计算这个平坦界面里的背景场 `E_bg`。然后只把光栅凸起看成相对平坦背景的扰动。

同时，Floquet 周期边界也改了。旧代码隐含了一个限制：

```text
每条边界 facet 只有 1 个 Nedelec 边自由度
```

这只适合一阶 Nedelec。现在改成了高阶也可以用的形式：每条边上可以有多个 H(curl) 自由度，右边界自由度用左边界自由度的线性组合表示。

## 2. 几何和电场是什么

当前算例是二维截面，沿 `z` 方向不变。电场只求平面内两个分量：

```text
E(x, y) = (Ex(x, y), Ey(x, y), 0)
```

结构从上到下大概是：

```text
顶部 PML
空气区域
空气中的矩形光栅凸起
基座
底部 PML
```

左右两边是周期单元边界，使用 Floquet 准周期条件：

```text
E(x + period_x, y) = exp(i kx period_x) E(x, y)
```

其中：

```text
kx = k0 n_air sin(theta)
k0 = 2 pi / lambda0
```

## 3. 强形式：程序真正求的 Maxwell 方程

频域 Maxwell 方程可以写成：

```text
curl(mu_r^{-1} curl(E)) - k0^2 epsilon_r E = 0
```

这里默认非磁性材料：

```text
mu_r = 1
```

所以物理区域里就是：

```text
curl curl(E) - k0^2 epsilon_r E = 0
```

因为我们只求二维平面内电场：

```text
E = (Ex, Ey, 0)
```

它的 curl 只有 z 分量：

```text
curl(E) = (0, 0, dEy/dx - dEx/dy)
```

这就是代码里 `curl_3d(field)` 的含义。

## 4. 为什么要写成散射场形式

直接求总场 `E_total` 也可以，但需要在端口边界上准确施加入射波和出射波条件。COMSOL 的周期端口就是在做这件事。

本代码当前采用的是散射场思想：

```text
E_total = E_bg + E_scat
```

其中：

```text
E_bg    背景场，已知或解析给出
E_scat  结构扰动引起的修正场，需要有限元求解
```

真实结构的总场满足：

```text
curl curl(E_total) - k0^2 epsilon_actual E_total = 0
```

把：

```text
E_total = E_bg + E_scat
```

代入：

```text
curl curl(E_bg + E_scat) - k0^2 epsilon_actual (E_bg + E_scat) = 0
```

展开：

```text
curl curl(E_scat) - k0^2 epsilon_actual E_scat
  = -[curl curl(E_bg) - k0^2 epsilon_actual E_bg]
```

背景场 `E_bg` 自己满足背景介质中的 Maxwell 方程：

```text
curl curl(E_bg) - k0^2 epsilon_background E_bg = 0
```

所以：

```text
curl curl(E_bg) = k0^2 epsilon_background E_bg
```

代回去：

```text
curl curl(E_scat) - k0^2 epsilon_actual E_scat
  = k0^2 (epsilon_actual - epsilon_background) E_bg
```

这就是代码第 277 行的公式：

```python
L = cfg.k0**2 * (eps - eps_bg) * inner(E_background, v) * d_physical
```

## 5. 旧版和新版的核心区别

### 5.1 旧版：空气背景

旧版设置：

```text
scattering_background = "air"
```

背景介电常数：

```text
epsilon_background = epsilon_air
```

背景场：

```text
E_bg = E_air
```

也就是空气中的解析平面波：

```text
E_air = p exp(i(kx x + ky y))
```

散射源变成：

```text
k0^2 (epsilon_actual - epsilon_air) E_air
```

因此，只要基座介电常数不等于空气：

```text
epsilon_substrate != epsilon_air
```

整块基座都会成为散射源。

这不是说旧版“没有考虑基座”。旧版左端的真实材料 `epsilon_actual` 是包含基座的。问题在于它把基座看成相对于全空气背景的扰动。

### 5.2 新版：平坦空气/基座分层背景

新版设置：

```text
scattering_background = "layered"
```

背景介电常数按平坦结构定义：

```text
空气区: epsilon_background = epsilon_air
基座区: epsilon_background = epsilon_substrate
```

这样平坦基座本身不再是散射源。只有光栅凸起所在区域，因为真实材料是 SiO2，而背景那里本来是空气，所以源项主要来自：

```text
epsilon_grating - epsilon_air
```

这更接近 COMSOL 周期端口里“上方入射、下方出射、基座作为端口背景的一部分”的设定。

## 6. 分层背景场是怎么计算的

新版背景场 `E_bg` 是平坦空气/基座界面的解析解。界面位于：

```text
y = 0
```

上方是空气，下方是基座。

入射波横向波数：

```text
kx = k0 n_air sin(theta)
```

空气中竖向波数：

```text
k_air_y = sqrt((k0 n_air)^2 - kx^2)
```

基座中竖向波数：

```text
k_sub_y = sqrt((k0 n_substrate)^2 - kx^2)
```

代码里用 `_positive_sqrt()` 选择合适的平方根，避免选到传播方向错误或衰减方向错误的根。

入射波写成：

```text
E_inc = p_inc exp(i(kx x - k_air_y y))
```

反射波写成：

```text
E_ref = r p_ref exp(i(kx x + k_air_y y))
```

透射波写成：

```text
E_trn = t p_trn exp(i(kx x - k_sub_y y))
```

其中偏振方向是平面内电场方向：

```text
p_inc = (cos_i,  sin_i)
p_ref = (cos_i, -sin_i)
p_trn = (cos_t,  sin_t)
```

反射系数和透射系数由平坦界面连续条件得到：

```text
r = (n_air cos_t - n_substrate cos_i)
    / (n_air cos_t + n_substrate cos_i)

t = 2 n_air cos_i
    / (n_air cos_t + n_substrate cos_i)
```

这里用的是平面内电场，也就是类似 TM/p 偏振的关系。物理含义是：在界面上，切向电场和切向磁场连续。

最后：

```text
空气侧: E_bg = E_inc + E_ref
基座侧: E_bg = E_trn
```

代码中对应 `solve_vector_maxwell.py` 第 62-95 行。

## 7. 弱形式：强形式如何变成 FEniCS 能算的形式

强形式是：

```text
curl curl(E_scat) - k0^2 epsilon_actual E_scat
  = k0^2 (epsilon_actual - epsilon_background) E_bg
```

为了用有限元求解，需要乘以测试函数 `v`，并在区域内积分。

对于复数问题，测试函数要取复共轭。代码中的：

```python
ufl.inner(a, b)
```

在复数模式里可以理解为：

```text
a · conj(b)
```

所以弱形式是：寻找 `E_scat`，使任意测试函数 `v` 都满足：

```text
integral[ curl(E_scat) · conj(curl(v)) ] dOmega
- k0^2 integral[ epsilon_actual E_scat · conj(v) ] dOmega
= k0^2 integral[ (epsilon_actual - epsilon_background) E_bg · conj(v) ] dOmega
```

对应代码的物理区域部分是：

```python
inner(curl_3d(u), curl_3d(v)) * d_physical
- k0**2 * eps * inner(u, v) * d_physical
```

右端项是：

```python
k0**2 * (eps - eps_bg) * inner(E_background, v) * d_physical
```

这里：

```text
u 是未知的 E_scat
v 是测试函数
eps 是真实介电常数 epsilon_actual
eps_bg 是背景介电常数 epsilon_background
E_background 是背景场 E_bg
```

## 8. PML 在弱形式里怎么出现

PML 的思想是把坐标变成复坐标，让出射波进入 PML 后指数衰减。当前只在 y 方向做复坐标延拓，并采用官方 DOLFINx PML demo 的形式。

由于本项目的物理区域不是关于 `y=0` 对称，代码先把 y 平移到物理区域中心：

```text
eta = y - y_center
```

然后使用：

```text
eta' = eta + i * alpha / k0 * eta * (|eta| - l_dom/2) / (l_pml/2 - l_dom/2)^2
```

最后平移回：

```text
y' = y_center + eta'
```

这里 `l_dom` 是不含 PML 的物理高度，`l_pml` 是把当前方向 PML 厚度计入后的等效总高度。

变换光学会把 PML 写成各向异性材料张量：

```text
epsilon_pml = det(J) J^{-1} epsilon_background J^{-T}
mu_pml      = det(J) J^{-1} mu_background      J^{-T}
```

代码中 PML 部分的弱式是：

```python
inner(inv(mu_pml) * curl_3d(u), curl_3d(v))
- k0**2 * inner(eps_pml * field_3d(u), field_3d(v))
```

顶部 PML 使用空气背景，底部 PML 使用基座背景。这样底部 PML 是基座向下的复坐标延拓，而不是在基座下面人为插入空气层。

## 9. Floquet 周期边界的数学意思

左右边界不是普通周期，而是带相位的周期：

```text
E_right(y) = exp(i kx period_x) E_left(y)
```

记：

```text
phase = exp(i kx period_x)
```

那么连续场层面就是：

```text
E(x_max, y) = phase E(x_min, y)
```

但是 Nedelec 元素的自由度不是简单的节点值。H(curl) 边元的自由度本质上是边上的切向积分或切向矩：

```text
dof_j(E) = integral_edge (E · t) q_j ds
```

一阶 Nedelec 每条边通常只有一个这样的自由度，所以旧代码可以简单地做：

```text
右边某个 dof = phase * 左边对应 dof
```

高阶 Nedelec 一条边有多个自由度，因此必须写成：

```text
右边第 i 个 dof = sum_j coefficient_ij * 左边第 j 个 dof
```

代码现在就是这么做的。

## 10. 高阶 Floquet 约束如何自动构造

对每一对左右边界 facet，代码构造一些探针场：

```text
F_m(x, y) = (0, eta^m exp(i kx x))
```

其中：

```text
eta = (y - y_mid) / y_scale
```

这些探针场用于“测量”左右边界上的 Nedelec 自由度。

设：

```text
L[j, m] = 左边第 j 个 dof 作用在探针场 F_m 上的值
R[i, m] = 右边第 i 个 dof 作用在探针场 F_m 上的值
```

我们希望找到矩阵 `T`：

```text
R ≈ phase * T * L
```

所以：

```text
T ≈ (R / phase) * pinv(L)
```

其中 `pinv(L)` 是伪逆。最后真正用于约束的系数是：

```text
coefficients = phase * T
```

于是每个右边界 slave 自由度都写成：

```text
slave_i = sum_j coefficients[i, j] master_j
```

这个形式既能给 `dolfinx_mpc` 官方接口，也能给手写矩阵消元。

## 11. 手写矩阵消元版本如何使用约束

假设完整未知量是：

```text
x
```

其中一部分自由度是 slave，需要由 master 表示。我们定义一个约束矩阵：

```text
x = C q
```

这里：

```text
q 是去掉 slave 后的自由未知量
C 把自由未知量重建成完整未知量
```

原始线性系统是：

```text
A x = b
```

代入 `x = C q`：

```text
A C q = b
```

为了得到对称的约束投影形式，左乘 `C^H`：

```text
C^H A C q = C^H b
```

这里 `C^H` 是 `C` 的共轭转置。代码中：

```python
A_reduced = C.conjugate().transpose() @ A_csr @ C
b_reduced = C.conjugate().transpose() @ b
```

求出 `q` 后：

```text
x = C q
```

这就是手写矩阵版 Floquet 约束的核心。

## 12. 如何使用旧版本

旧版本使用全空气背景。命令：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both --scattering-background air"
```

或者不写 `--scattering-background air` 也可以，因为默认就是 `air`：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both"
```

适合用途：

```text
检查原始空气背景散射模型
和旧结果保持一致
理解基座相对空气背景产生的整体修正场
```

## 13. 如何使用新版本

新版使用平坦空气/基座背景。命令：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both --scattering-background layered"
```

使用二阶 Nedelec：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both --scattering-background layered --nedelec-degree 2"
```

如果只是快速检查程序是否能跑，可以先粗一些：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both --scattering-background layered --nedelec-degree 2 --mesh-target-size 60.0 --visualization-degree 2"
```

## 14. 常用参数怎么改

这些参数在 `src/common/config.py` 中：

```text
period_x               周期长度，单位 nm
air_height             物理空气层高度，单位 nm
substrate_thickness    基座厚度，单位 nm
pml_top_thickness      顶部 PML 厚度，单位 nm
pml_bottom_thickness   底部 PML 厚度，单位 nm
grating_width          光栅宽度，单位 nm
grating_height         光栅高度，单位 nm
lambda0                真空波长，单位 nm
incident_angle_deg     入射角，单位 degree
n_air                  空气折射率
n_substrate            基座折射率
n_grating              光栅折射率
scattering_background  air 或 layered
nedelec_degree         Nedelec 边元阶次
visualization_degree   输出到 ParaView 前插值用的 DG 阶次
mesh_target_size       网格目标尺寸，单位 nm
pml_alpha              PML 吸收强度
```

建议：

```text
想更接近 COMSOL 周期端口结果: scattering_background = layered
想提高有限元精度: nedelec_degree = 2
想先快速试跑: mesh_target_size 调大，例如 50.0 或 60.0
想正式算图: mesh_target_size 调小，例如 15.0 或 10.0
PML 不够吸收: 优先加厚 pml_top_thickness/pml_bottom_thickness
PML 反射变差: 不要盲目把 pml_alpha 加到很大
```

## 15. 代码逐行讲解：`config.py`

| 行号 | 作用 |
|---|---|
| 1 | 开启 Python 的未来注解功能，让类型标注更稳定。 |
| 3-5 | 导入 dataclass、数学函数和路径工具。 |
| 7 | 导入 NumPy，用于复指数和数组。 |
| 10-20 | 定义区域标签。空气是 1，基座是 2，光栅是 3，上下 PML 是 4 和 5，左右 Floquet 边界是 11 和 12。 |
| 23-25 | 定义 `SimulationConfig`，所有算例参数集中放在这里。 |
| 27-38 | 设置几何、波长、入射角和材料折射率。长度单位都是纳米。 |
| 39 | 本次新增的 `scattering_background`。`air` 是旧版，`layered` 是新版。 |
| 41 | `nedelec_degree` 控制 Nedelec 边元阶次，现在可以调到 2 或更高阶进行测试。 |
| 42 | `visualization_degree` 控制输出到 ParaView 前的 DG 插值阶次，不是求解阶次。 |
| 43 | `mesh_target_size` 控制网格尺寸。越小越精细，也越慢。 |
| 44 | `pml_alpha` 控制 PML 吸收强度。不是越大越好。 |
| 47-57 | 把折射率转成相对介电常数：`epsilon = n^2`。 |
| 59-61 | 把角度从 degree 转成 rad。 |
| 63-65 | 计算真空波数 `k0 = 2 pi / lambda0`。 |
| 67-69 | 计算角频率 `omega`，主要用于记录。 |
| 71-77 | 计算入射波矢的 `kx` 和 `ky`。当前入射波从上往下走，所以 `ky` 为负。 |
| 79-81 | 给出入射平面内偏振方向。 |
| 83-85 | 计算 Floquet 相位 `exp(i kx period_x)`。 |
| 87-137 | 根据几何参数计算上下边界、光栅位置等派生量。 |
| 139-150 | 把配置转成 JSON 可保存形式，并补充计算得到的 `k0`、`kx`、`epsilon` 等。 |
| 153-154 | 返回项目根目录。 |

## 16. 代码逐行讲解：`materials.py`

| 行号 | 作用 |
|---|---|
| 1-7 | 导入依赖。 |
| 10 | 定义真实介电常数函数 `relative_permittivity`。 |
| 12 | 创建 DG0 空间。DG0 表示每个单元一个常数，适合分片常数材料。 |
| 13 | 创建名为 `epsilon_r` 的有限元函数。 |
| 14 | 先把所有单元设为空气介电常数。 |
| 16-17 | 找到基座单元和光栅单元。 |
| 18 | 把基座单元改成 `epsilon_substrate`。 |
| 19 | 把光栅单元改成 `epsilon_grating`。 |
| 20 | 同步并行数据。 |
| 21 | 返回真实材料 `epsilon_actual`。 |
| 24 | 定义背景介电常数函数 `background_relative_permittivity`。 |
| 26 | 同样使用 DG0 空间。 |
| 27 | 创建名为 `epsilon_background` 的有限元函数。 |
| 28 | 默认背景全设为空气。 |
| 30-31 | 如果背景是 `air`，不做额外修改，保持全空气背景。 |
| 32-34 | 如果背景是 `layered`，把基座区域改成基座介电常数。 |
| 35-36 | 如果参数不是 `air` 或 `layered`，报错。 |
| 38-39 | 同步数据并返回背景材料。 |

## 17. 代码逐行讲解：`solve_vector_maxwell.py` 的背景场部分

| 行号 | 作用 |
|---|---|
| 1-22 | 导入依赖和本项目模块。新增导入了 `background_relative_permittivity`。 |
| 25-27 | 把 PETSc 矩阵转成 SciPy CSR 矩阵，给手写矩阵消元使用。 |
| 30-37 | 定义 JSON 保存时如何处理复数、NumPy 数值和路径。 |
| 40 | 定义旧版空气平面波背景函数。 |
| 41 | 创建有限元函数 `E_inc`。 |
| 42 | 读取偏振方向 `(px, py)`。 |
| 44-49 | 对每个空间点计算 `E_inc = p exp(i(kx x + ky y))`。 |
| 51 | 把解析表达式插值到 Nedelec 空间。 |
| 52 | 返回旧版空气背景场。 |
| 55-59 | 选择平方根的物理分支，用于计算分层背景里的竖向波数。 |
| 62 | 定义新版分层背景场函数。 |
| 63 | 创建 `E_background_layered`。 |
| 64 | 计算空气里的竖向波数 `k_air_y`。 |
| 65 | 计算基座里的竖向波数 `k_sub_y`。 |
| 67-70 | 计算入射角和折射角对应的正弦、余弦。 |
| 72-75 | 计算平坦空气/基座界面的反射系数 `r` 和透射系数 `t`。 |
| 77-79 | 定义入射、反射、透射电场的偏振方向。 |
| 81-92 | 对每个点计算背景场。空气侧用 `E_inc + E_ref`，基座侧用 `E_trn`。 |
| 94-95 | 插值并返回分层背景场。 |
| 98-103 | 根据 `scattering_background` 在旧版空气背景和新版分层背景之间切换。 |

对应公式是：

```text
air 模式:
E_bg = E_air
epsilon_bg = epsilon_air

layered 模式:
E_bg = E_inc + E_ref    y >= 0
E_bg = E_trn            y < 0
epsilon_bg = epsilon_air 或 epsilon_substrate
```

## 18. 代码逐行讲解：`solve_vector_maxwell.py` 的求解主流程

| 行号 | 作用 |
|---|---|
| 106-147 | 官方 `dolfinx_mpc` 低层接口求解函数。 |
| 112 | 创建 `MultiPointConstraint` 对象。 |
| 113-118 | 把 slave、master、系数和 offsets 传给 `mpc.add_constraint`。这是高阶 Floquet 约束的入口。 |
| 119 | 结束约束构建。 |
| 121-134 | 创建线性问题，使用 LU 直接求解。 |
| 135-147 | 求解并返回求解器信息。 |
| 150-198 | 官方自动周期 helper 的尝试入口。注意它对当前高阶 H(curl) 场不是主要路线。 |
| 201-209 | 手写矩阵版的求解包装，调用 `solve_with_constraints`。 |
| 212-214 | `run_case` 是单个算例的主函数。 |
| 215-222 | 创建输出目录、日志和计时。 |
| 224-225 | 检查 PETSc 是否为复数模式。频域 Maxwell 必须使用复数。 |
| 227-236 | 打印算例名、波数、偏振、背景模式和 Floquet 相位。 |
| 238 | 构建网格。 |
| 243-244 | 创建 Nedelec `N1curl` 函数空间。`cfg.nedelec_degree` 就在这里生效。 |
| 249 | 构建真实介电常数 `eps = epsilon_actual`。 |
| 250 | 构建背景介电常数 `eps_bg = epsilon_background`。 |
| 251 | 构建背景场 `E_background`。 |
| 252 | 构建 Floquet 约束。 |
| 253-257 | 打印 Floquet 约束检查指标。 |
| 259-260 | 创建 trial/test 函数，未知量 `u` 表示 `E_scat`。 |
| 261 | 获取空间坐标。 |
| 262-265 | 定义不同区域上的积分 measure。 |
| 267-268 | 计算上下 PML 张量。 |
| 269-276 | 组装双线性形式 `a(u, v)`，也就是左端 Maxwell 算子。 |
| 277 | 组装线性形式 `L(v)`，也就是散射源项。新版和旧版的差别集中在这里的 `eps_bg` 和 `E_background`。 |
| 279-286 | 如果使用官方 MPC，就调用 `dolfinx_mpc` 版本。 |
| 287-301 | 如果使用手写矩阵版，就组装矩阵、向量并做约束消元。 |
| 305-307 | 计算总场：`E_total = E_background + E_scat`。 |
| 309 | 保存 ParaView 文件和图片。 |
| 310-312 | 计算散射强度比和 Floquet mismatch。 |
| 315-350 | 生成 `run_summary.json` 里的摘要信息。 |
| 351-359 | 打印关键结果。 |
| 361-366 | 写入 `run_summary.json` 和 `solver_log.txt`。 |
| 368 | 返回摘要。 |

## 19. 代码逐行讲解：`floquet_constraint.py`

| 行号 | 作用 |
|---|---|
| 1-11 | 导入依赖。 |
| 14-23 | 定义 Floquet 约束数据结构。现在包含 `coefficients` 和 `offsets`，支持一个 slave 对多个 master。 |
| 26-30 | 给定某条边界 facet，找到它上面的 H(curl) 自由度。高阶时会返回多个 dof。 |
| 33-39 | 定义局部约束矩阵构造函数。 |
| 40-45 | 统计左右边 dof 数量，并准备探针矩阵。 |
| 47 | 循环构造多个探针场。 |
| 48 | 创建一个临时有限元函数作为探针。 |
| 50-54 | 定义探针场 `F_m = (0, eta^m exp(i kx x))`。 |
| 56-59 | 把探针场插值到空间里，并记录左右边界自由度上的值。 |
| 61-66 | 检查探针场是否足够丰富。如果秩不够，就不能可靠重构高阶自由度。 |
| 68 | 用伪逆计算 `transform = (R / phase) pinv(L)`。 |
| 69-71 | 计算重构误差，返回变换矩阵和误差。 |
| 74 | 定义总的 Floquet 约束构造函数。 |
| 76-81 | 找到左右 Floquet facets，并检查数量是否一致。 |
| 83-90 | 按 y 坐标对左右边界 facet 排序。 |
| 91-93 | 检查左右边界是否能一一配对。 |
| 95-100 | 准备 slave、master、系数和误差列表。 |
| 102 | 逐对处理左右 facet。 |
| 103-104 | 获取这一对 facet 上的 H(curl) 自由度。 |
| 105-109 | 检查左右 dof 数量是否一致。 |
| 111-118 | 调用探针矩阵方法，得到这一对 facet 的高阶 Floquet 变换。 |
| 120 | 设置很小系数的截断阈值，避免把数值噪声写进约束。 |
| 121-138 | 把每个右边界 slave dof 写成左边界 master dof 的线性组合。 |
| 140-149 | 返回完整约束数据。 |
| 152-180 | 手写矩阵版使用约束：构造 `C`，解 `C^H A C q = C^H b`，再还原完整解。 |
| 183-195 | 检查求出的场是否满足 Floquet 约束。 |

核心公式：

```text
slave_i = sum_j coefficients[i, j] master_j
x = C q
C^H A C q = C^H b
```

## 20. 代码逐行讲解：`src/runners/run_cases.py`

| 行号 | 作用 |
|---|---|
| 1-10 | 导入命令行解析、JSON、配置和求解函数。 |
| 13 | 定义命令行入口。 |
| 14-20 | 添加 `--constraint-backend`，控制使用官方 MPC、手写矩阵版或两个都跑。 |
| 21-26 | 添加 `--scattering-background`，控制旧版 `air` 或新版 `layered`。 |
| 27 | 添加 `--nedelec-degree`，控制 Nedelec 边元阶次。 |
| 28 | 添加 `--visualization-degree`，控制输出插值阶次。 |
| 29 | 添加 `--mesh-target-size`，控制网格粗细。 |
| 30 | 解析命令行参数。 |
| 32-37 | 根据参数自动拼接算例名。 |
| 39-48 | 把命令行参数写入 `SimulationConfig`。 |
| 50 | 创建基础配置。 |
| 51 | 如果选择 `both`，就同时跑 `mpc_official` 和 `manual`。 |
| 52-56 | 循环运行每个后端，并把结果保存到对应目录。 |
| 58-62 | 写出所有运行摘要。 |
| 63-79 | 如果两个后端都跑了，就写出两者对比结果。 |
| 82-83 | 作为模块运行时进入 `main()`。 |

## 21. 和 COMSOL 对比时应该看什么

建议优先比较：

```text
E_total_abs
E_total_Ex_real
E_total_Ey_real
```

不要一开始就比较 PML 区域。PML 是数值吸收层，不同软件的内部变量定义不一定一致。

也不要直接拿旧版 `air` 背景的 `E_scat_abs` 去和 COMSOL 的 scattered field 比，因为两者的背景定义不同。

更合理的对比顺序是：

```text
1. 使用 scattering_background = layered
2. 比较物理区域中的 E_total_abs
3. 确认入射振幅单位是否一致
4. 再比较 Ex/Ey 实部条纹
5. 最后再讨论反射/透射功率或 S 参数
```

## 22. 当前版本的局限

当前新版已经把背景从“全空气”改成了“平坦空气/基座”，但它仍然不是完整的 COMSOL 周期端口实现。

COMSOL 周期端口会自动做：

```text
入射模态
反射模态
透射模态
可能的 Floquet 衍射级次
端口功率归一化
```

原来的分层背景散射版本没有显式做这些端口模态展开。因此它会更接近 COMSOL，但还不能保证逐点完全一致。

现在若要继续逼近 COMSOL，应使用新增端口法：

```text
--formulation port_total --constraint-backend manual --port-order-count N
```

它已经实现 `m=-N...N` 的 Fourier 周期端口。后续如果还要继续完善，可再增加反射/透射衍射级次功率提取、S 参数和功率流积分。

配置式运行时，对应写法是：

```python
calculation_method = "port"
constraint_backend = "manual"
port_boundary_model = "dtn"
port_dtn_order_count = N
```

## 23. 快速记忆版

最重要的一句话：

```text
旧版 air:     基座也是相对空气背景的散射源
新版 layered: 平坦基座属于背景，主要只让光栅凸起作为散射源
```

最常用运行命令：

```powershell
& "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe" run --rm -v "C:\Users\admin\Desktop\Code:/work" -w /work code-dolfinx-mpc:latest sh -lc ". dolfinx-complex-mode && python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main --constraint-backend both --scattering-background layered --nedelec-degree 2"
```

最重要输出文件：

```text
fields_for_paraview.vtu
run_summary.json
solver_log.txt
backend_comparison.json
```

## 24. 2026-06-09 补充：分层背景法和端口法的关系

本文件主要解释 `scattering_background = "layered"`，也就是“平坦空气/基座背景 + 光栅扰动散射”。它仍然属于散射场法，未知量是：

```text
E_scat = E_total - E_bg
```

现在新增的端口总场法入口是：

```text
--formulation port_total
```

它不再先构造 `E_bg`，而是直接求：

```text
E_total
```

上端口把入射 Floquet 基模写入边界右端，下端口作为出射端口。两侧 Floquet 周期约束、高阶 Nedelec 约束处理、材料分区和 ParaView 输出仍复用本文件讲过的基础设施。

因此现在有三种常用对比层级：

```text
scattered + air       最早版本，全空气背景
scattered + layered   分层背景散射，更适合解释光栅扰动
port_total            端口总场，更适合对照 COMSOL 周期端口图
```

详细端口推导和新增代码逐行说明见：

```text
port_total_formulation_and_run_management.md
```

若要让端口法进一步包含 COMSOL 常见的多个衍射级次，可以运行：

```text
--formulation port_total --constraint-backend manual --port-order-count N
```

这里 `N` 表示保留 `m=-N...N` 的 Floquet 端口模态。它不改变本文件所讲的材料和 Floquet 周期边界，只改变上下端口的出射算子。
