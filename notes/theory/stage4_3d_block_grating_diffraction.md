# Stage 4 理论说明：3D 周期矩形柱与衍射级后处理

## 2026-06-25 更新：为什么官方 R/T 改为 E/H Fourier

对一个给定衍射级 `(m,n)`，横向波矢 `k_t=(alpha,gamma)` 是固定的，但在同一个 probe 面上可以同时存在：

```text
down wave: k_z = -beta
up wave:   k_z = +beta
```

如果只取电场 Fourier 系数 `E_mn(z_probe)`，它实际是 down 与 up 的叠加。有限 PML、外边界反射或数值近场都会让同一个 `(m,n)` 同时含有两个方向。此时 E-only 后处理会把 incoming/outgoing 混在一起，典型表现就是透射率被抬高，甚至 `R+T>1`。

当前官方口径改为对每个 `(m,n)` 使用切向场：

```text
[E_x, E_y, H_x, H_y]_mn
```

建立一个小的方向/偏振模态系统：

```text
[E_t, H_t]_mn =
  a_down_s [E_t,H_t]_{down,s}
+ a_down_p [E_t,H_t]_{down,p}
+ a_up_s   [E_t,H_t]_{up,s}
+ a_up_p   [E_t,H_t]_{up,p}
```

然后只统计：

```text
top:    up   amplitudes -> reflected power
bottom: down amplitudes -> transmitted power
```

这相当于一个轻量级的 modal-port 后处理，不改变有限元求解矩阵。旧 E-only 结果仍保留为诊断字段，用来判断 E-only 误差有多大。

注意：E/H Fourier 修正只能修后处理中的方向混叠，不能修复场解本身。如果有限元解已经因为网格过粗、PML 多级次反射、或 3D H(curl) 离散问题产生非物理场，那么 E/H Fourier 仍会给出 `R+T>1`，此时结果必须标记为 diagnostic-only。

## 2026-06-23 更新：为什么 0 级传播时仍要拟合 evanescent 级次

默认矩形柱参数为：

```text
lambda0 = 633 nm
period_x = 350 nm
period_y = 300 nm
n_air = 1
n_substrate = 1.45
```

在这个周期下，远场传播功率基本只需要统计 `(m,n)=(0,0)` 级，因为更高阶在空气/基底中多为 evanescent，不携带远场功率。

但是探测面离 grating 有限距离，数值场仍包含非传播近场谐波：

```text
E_probe = E_00_propagating + sum(E_mn_evanescent)
```

如果拟合基只放 0 级，evanescent 近场会被最小二乘错误地塞进 0 级幅值，导致：

```text
R/T 偏大
R+T 可能超过 1
fit residual 较高
```

因此当前 Stage 4 的做法是：

```text
1. 默认仍只把传播级次计入 R/T 总功率；
2. 但对 block grating 的模态拟合，额外加入邻近 evanescent 级次；
3. evanescent 级次的行会写入 diffraction_orders_3d.json/csv，
   但 included_in_total_power=false，不进入 R_total/T_total。
```

最新 h50/p1 串行结果显示这个修正是必要的：

```text
只拟合 0 级时：R+T 约 1.054
加入邻近 evanescent 拟合后：R+T = 0.982634
top fit residual 从约 1.6e-2 降到约 4.1e-3
```

这并不代表 h50/p1 已可做最终定量 benchmark；它只说明后处理不再把近场谐波误认为传播功率。最终还需要网格收敛、探测面位置收敛和 2.5D 对照继续验证。

## 2026-06-23 更新：第一版公式口径

Stage 4 不再继续推进 2.5D 复现，也不把 Stage 2 的 2B/2C 当作硬门槛。新的主线是直接求解一个真实 3D 周期单胞：

```text
air / grating block / substrate / z-PML / x-y Floquet
```

## 分层背景散射场法

总场写成：

```text
E_total = E_bg + E_scat
```

其中 `E_bg` 是没有 grating 时的空气/基底平界面 Fresnel 分层场。它包含：

```text
air side:      incident + reflected
substrate:     transmitted
```

求解未知量是 `E_scat`。弱式右端使用：

```text
L(v) = k0^2 * (eps_true - eps_bg) * inner(E_bg, v)
```

积分区域只放在真实结构和背景不同的物理区域。默认矩形柱坐在空气中、位于 `z=0` 之上，所以：

```text
source tag = grating
eps_true = n_grating^2
eps_bg = n_air^2
```

air、substrate、top_pml、bottom_pml 都不放 source。PML 内的材料背景按上下介质选择：

```text
top PML: air background
bottom PML: substrate background
```

## Floquet 约束

Stage 4 沿用低内存显式拓扑 Floquet：

```text
slave_dof = phase * orientation_sign * master_dof
x=Lx -> x=0: phase = exp(i kx Lx)
y=Ly -> y=0: phase = exp(i ky Ly)
corner edge: phase = exp(i(kx Lx + ky Ly))
```

第一版只支持：

```text
hexahedron
degree=1 N1curl
one slave dof -> one master dof
```

不再使用 probe function、pseudo-inverse 或 whole-plane dense transform。

## 衍射级模式

每个衍射级 `(m,n)` 的横向波矢为：

```text
alpha_m = kx + 2*pi*m/Lx
gamma_n = ky + 2*pi*n/Ly
```

在介质 `n_j` 中：

```text
beta_j = sqrt((k0*n_j)^2 - alpha_m^2 - gamma_n^2)
```

`beta_j` 取实部为正、或虚部为正的分支。若该级次传播，则计入总反射/透射功率；若接近 Rayleigh anomaly，则在输出中标记 `rayleigh_warning`。

## 偏振基

当横向波矢不为零时使用 `s/p` 基：

```text
s = (-gamma, alpha, 0) / |kt|
p = direction x s
```

当 `kt=0` 时，`s/p` 方向退化，程序使用固定的 `x/y` 线偏振基。

## 功率归一化

后处理在 top/bottom PML 前的均匀层采样 `E_t,H_t`。对每个模式构造单位幅值的 `E,H`，用：

```text
S = 0.5 * Re(E x conj(H))
```

计算单位幅值模式穿过单胞面积的功率。反射使用 top 上行波，透射使用 bottom 下行波，并除以入射波功率：

```text
R_mn = |a_ref_mn|^2 * P_ref_unit / P_inc
T_mn = |a_trn_mn|^2 * P_trn_unit / P_inc
```

只把 propagating orders 加到：

```text
R_total
T_total
A_balance = 1 - R_total - T_total
```

## FE 响应校准

低阶 Nedelec 插值后，直接点采样拟合平面波幅值会有系统偏置。Stage 4 的 diffraction 后处理会对每个候选模式做一次小型响应校准：

```text
1. 把单位幅值模式插值到同一个 Nedelec space
2. 用同一套 probe plane 和 H=curl(E) 后处理拟合它的 apparent amplitude
3. 组装一个小响应矩阵
4. 用这个矩阵反解真实模态幅值
```

这个步骤已通过 `stage4_flat_layer_sanity` 验证：无 grating/source 时，数值后处理能回到 Fresnel 解析 0 级 R/T。

## 当前限制

```text
1. 还没有 3D modal port 边界条件。
2. 还没有装配 Q*YQ 或 auxiliary modal port 方程。
3. diffraction 后处理第一版默认只使用 0 级；高阶传播可通过 CLI 打开。
4. h50/p1 block grating 已跑通，但 R+T 还有粗网格/PML/边界误差。
5. tetra mesh 和 degree>1 Floquet 仍明确报 NotImplementedError。
```
