# TE 偏振、复折射率和吸收率补充说明

本文记录本次新增内容：在保留原有 TM 矢量 Maxwell 算例的基础上，增加 TE 标量 `Ez` 算例、复数折射率和吸收率后处理。这里的公式按代码实际采用的时间因子

```text
exp(-i omega t)
```

来写。

## 1. TM 和 TE 分别是什么

当前项目仍然是二维截面模型，结构沿 `z` 方向不变。

TM，也就是原来的代码，未知量是平面内电场：

```text
E = (Ex, Ey, 0)
H = (0, 0, Hz)
```

它必须使用 `H(curl)` 空间和 Nedelec 边元，因为 `Ex/Ey` 在介质界面上要满足切向连续条件。这个分支仍然在：

```text
src/solvers/solve_vector_maxwell.py
src/solvers/solve_port_maxwell.py
```

TE 是新加的分支，未知量是垂直纸面的标量电场：

```text
E = (0, 0, Ez)
H = (Hx, Hy, 0)
```

因为未知量只有 `Ez` 一个标量，所以使用普通 Lagrange 标量空间，不再使用 Nedelec 边元。这个分支在：

```text
src/solvers/solve_te_maxwell.py
```

在 `src/main.py` 或 `src/common/config.py` 中可以选择：

```python
POLARIZATION_TYPE = "TM"
POLARIZATION_TYPE = "TE"
```

命令行等价选项是：

```bash
--polarization-type TM
--polarization-type TE
```

## 2. 复数折射率的约定

现在材料折射率允许写成复数：

```python
n_air = 1.0 + 0.0j
n_substrate = 1.45 + 0.0j
n_grating = 1.45 + 0.02j
```

代码仍然使用：

```text
epsilon_r = n^2
```

如果时间因子是 `exp(-i omega t)`，被动吸收材料通常写成：

```text
epsilon_r = epsilon' + i epsilon''
epsilon'' > 0
```

也就是说 `n = n_real + i n_imag` 且 `n_imag > 0` 时通常表示吸收。所有复数会在 JSON 中写成：

```json
[real, imag]
```

例如：

```json
"n_grating": [1.45, 0.02]
```

## 3. TE 强形式

TE 中只有 `Ez`，在非磁性材料 `mu_r=1` 下满足标量 Helmholtz 方程：

```text
laplace(Ez) + k0^2 epsilon_r Ez = 0
```

其中：

```text
k0 = 2 pi / lambda0
```

为了写成有限元弱式，把方程乘以测试函数的共轭 `conj(v)`，再在区域内积分：

```text
int_Omega [laplace(Ez) conj(v) + k0^2 epsilon_r Ez conj(v)] dOmega = 0
```

对 Laplace 项做分部积分：

```text
int_Omega grad(Ez) . conj(grad(v)) dOmega
- k0^2 int_Omega epsilon_r Ez conj(v) dOmega
- int_boundary partial_n(Ez) conj(v) ds = 0
```

如果边界项先不写，体积分弱式就是：

```text
a(Ez, v)
= int grad(Ez) . conj(grad(v)) dOmega
  - k0^2 int epsilon_r Ez conj(v) dOmega
```

这就是 `solve_te_maxwell.py` 中 TE 物理区域的主弱式。

## 4. TE 散射场法

散射场法把总场拆成：

```text
Ez_total = Ez_background + Ez_scat
```

真实结构的介电常数是 `epsilon_actual`，背景介电常数是 `epsilon_background`。总场满足：

```text
laplace(Ez_total) + k0^2 epsilon_actual Ez_total = 0
```

背景场满足：

```text
laplace(Ez_background) + k0^2 epsilon_background Ez_background = 0
```

把 `Ez_total = Ez_background + Ez_scat` 代进去，并把背景方程相减，得到散射场强形式：

```text
laplace(Ez_scat) + k0^2 epsilon_actual Ez_scat
= -k0^2 (epsilon_actual - epsilon_background) Ez_background
```

对应到代码里的弱式右端项，符号会变成：

```text
L(v) = k0^2 int (epsilon_actual - epsilon_background)
       Ez_background conj(v) dOmega
```

这和原 TM 散射场法保持一致。

## 5. TE 分层背景 Fresnel 系数

当 `scattering_background="layered"` 时，空气/基座平界面被当成背景，光栅才是主要散射源。

定义：

```text
beta_air = sqrt((k0 n_air)^2 - kx^2)
beta_sub = sqrt((k0 n_substrate)^2 - kx^2)
```

TE 的平界面反射、透射系数是：

```text
r_TE = (beta_air - beta_sub) / (beta_air + beta_sub)
t_TE = 2 beta_air / (beta_air + beta_sub)
```

上方空气中：

```text
Ez_background = exp(i kx x - i beta_air y)
              + r_TE exp(i kx x + i beta_air y)
```

下方基座中：

```text
Ez_background = t_TE exp(i kx x - i beta_sub y)
```

注意这和 TM/p 偏振的 Fresnel 系数不同。

## 6. TE PML 弱式

TE 的 PML 使用同一个复坐标拉伸思想。若复坐标映射为：

```text
x_tilde = x_tilde(x, y)
```

Jacobian 为：

```text
J = d(x_tilde, y_tilde) / d(x, y)
```

标量 Helmholtz 方程在弱式中的梯度项要替换为：

```text
det(J) J^{-1} J^{-T}
```

质量项中的介电常数要乘：

```text
det(J)
```

因此 TE PML 弱式写成：

```text
int_PML [C grad(Ez) . conj(grad(v))
         - k0^2 epsilon_scaled Ez conj(v)] dOmega
```

其中：

```text
C = det(J) J^{-1} J^{-T}
epsilon_scaled = det(J) epsilon_background
```

代码位置：

```text
src/common/pml.py
top_scalar_pml_coefficients()
bottom_scalar_pml_coefficients()
```

## 7. 为什么端口法禁止 port_use_pml=True

端口总场法的设计是：上下外边界直接放 Robin 或 DtN 端口条件，因此它默认：

```python
port_use_pml = False
```

目前端口法的体积分只包含真实物理区：

```text
air/substrate/grating
```

如果强行令：

```python
port_use_pml = True
```

网格里会出现 PML 单元，但端口总场弱式没有把这些 PML 单元加入 Maxwell/PML 体积分。结果就是 PML 内自由度没有正确方程约束，可能出现“自由度悬空”的错误结果。

因此现在入口层和求解器层都会直接报错：

```text
port_use_pml=True is disabled for port total-field runs
```

如果后续要实现“端口 + PML”，需要重新推导端口总场在 PML 区域的弱式，不能只把 PML 网格打开。

## 8. TE 端口法

TE 端口法直接求总场 `Ez_total`。第 `m` 个 Floquet 级次为：

```text
alpha_m = kx + 2 pi m / period_x
beta_m = sqrt((k0 n)^2 - alpha_m^2)
```

向下波：

```text
Ez_down = A_down exp(i alpha_m x - i beta_m y)
```

向上波：

```text
Ez_up = A_up exp(i alpha_m x + i beta_m y)
```

定义缩放磁场：

```text
Hx_scaled = dEz/dy / i
```

那么：

```text
Hx_scaled_down = - beta_m Ez_down
Hx_scaled_up   = + beta_m Ez_up
```

所以后处理时可以拆成：

```text
Ez_down = 1/2 (Ez_m - Hx_scaled_m / beta_m)
Ez_up   = 1/2 (Ez_m + Hx_scaled_m / beta_m)
```

TE 的模态功率因子为：

```text
P_m_scaled = 0.5 Re(beta_m) |Ez_m|^2
```

公共常数 `1/(omega mu0)` 在分子分母中抵消，所以 R/T 是无量纲量。

## 9. DtN 端口的 TE 投影

TE DtN 端口不是重新在端口画一条采样线，而是复用装配端口矩阵时的压缩投影向量。也就是说，端口矩阵里用于 Fourier 模态的向量：

```text
ell_m(v) = int_port exp(i alpha_m x) conj(v) ds
```

会以压缩形式保存：

```text
非零 dof 索引 + 非零值
```

后处理时直接把它作用到有限元解向量上，得到端口面上的模态系数。这样 `dtn_port_power_metrics.json` 和 DtN 边界条件使用的是同一组端口投影。

相比之下：

```text
power_metrics.json
```

仍然是旧的水平探测线法。它适合和 scattered/Robin/DtN 统一对照，但对 DtN 端口而言，优先看：

```text
dtn_port_power_metrics.json
```

## 10. 吸收率

后处理现在同时输出两个吸收相关指标。

第一个是能量平衡余量：

```text
A_balance = 1 - R_total - T_total
```

第二个是体积分吸收：

```text
P_abs_scaled = 0.5 k0^2 int Im(epsilon_r) |E|^2 dOmega
A_volume = P_abs_scaled / P_inc_scaled
```

其中：

```text
TM: |E|^2 = |Ex|^2 + |Ey|^2
TE: |E|^2 = |Ez|^2
```

体积分只在真实材料区做：

```text
air/substrate/grating
```

不把 PML 计入材料吸收。

无损材料时，理论上：

```text
A_volume ≈ 0
```

如果 R/T 后处理足够准确，也应该有：

```text
A_balance ≈ 0
```

如果设置例如：

```python
n_grating = 1.45 + 0.02j
```

则通常应观察到：

```text
R_total + T_total < 1
A_balance > 0
A_volume > 0
```

并且在网格、端口级次、探测线都合理时：

```text
A_balance ≈ A_volume
```

## 11. 当前并行支持状态

TM：

```text
scattered + mpc_official: 支持 MPI
scattered + manual: 串行验证
port robin + mpc_official: 支持 MPI
port dtn + manual: 串行
```

TE：

```text
scattered + mpc_official: 支持 MPI，使用 dolfinx_mpc 自动标量周期约束
scattered + manual: 串行验证
port robin + mpc_official: 支持 MPI 的设计路径
port dtn + manual: 串行
```

DtN 端口目前仍是非局部矩阵算子，所以保留为串行 manual 路径。

## 12. 本次快速验证结果

本次用粗网格做了代码通路验证：

```text
TE scattered + manual: 可装配、可求解、可写出 Ez 和 R/T 文件
TE scattered + mpc_official: 可装配、可求解，最大场值与 manual 一致
TE port DtN + manual: 可装配、可求解，dtn_port_power_metrics.json 中 R+T ≈ 1
TM scattered + manual: 原 TM 路径仍可运行
port_use_pml=True: 在入口层正确报错
```

粗网格下的水平探测线 R/T 不能当作最终精度结论。特别是 DtN 端口法，应优先使用 `dtn_port_power_metrics.json` 中的端口面模态功率。
