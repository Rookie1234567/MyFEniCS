# Stage 4 理论说明：3D 周期矩形柱与衍射级后处理

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
