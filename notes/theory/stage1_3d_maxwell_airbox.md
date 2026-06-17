# Stage 1：3D Maxwell 空气盒子的理论约定

本阶段只验证 3D 主框架，不做 3D 光栅、Floquet、PML、DtN、modal port 或衍射级后处理。

## 方程

代码采用频域约定：

```text
E(r, t) = Re{ E(r) exp(-i omega t) }
```

在这个约定下，均匀介质中的电场方程写成：

```text
curl(mu_r^-1 curl E) - k0^2 eps_r E = 0
```

空气盒子里：

```text
eps_r = 1
mu_r = 1
```

未知量是完整三维电场：

```text
E = (Ex, Ey, Ez)
```

有限元空间使用 3D Nedelec H(curl) 单元。

## 平面波

解析平面波写成：

```text
E_exact = p exp(i k dot r)
```

它必须满足：

```text
|k| = k0 n
k dot p = 0
```

第二条是横波条件。代码不会悄悄修正错误偏振；如果 `k dot p` 不接近 0，会直接报错。

## 为什么第 1 步要用边界条件

只组装齐次 Maxwell 方程：

```text
curl curl E - k0^2 E = 0
```

并不能自动产生入射平面波。有限盒子里如果没有源项或边界条件，求解器通常会得到零解，或者遇到不适定问题。

所以第 1 步采用 manufactured solution 思路：在空气盒子六个外表面强制解析平面波的切向电场，也就是 H(curl) 的 essential boundary condition：

```text
n x E = n x E_exact
```

这样内部数值解应该重建解析平面波。这个测试用于检查：

```text
3D mesh 是否正确
3D Nedelec 空间是否正确
curl-curl 弱式是否正确
复数 PETSc/DOLFINx 是否正确
curl 后处理 H 是否正确
ParaView 输出是否正确
```

## 磁场单位

代码内部长度单位是微米，所以 `k0` 的单位是 `1/um`。

为了避免单位混乱，后处理同时输出两个磁场量：

```text
eta0_H = (1 / (i k0 mu_r)) curl_um(E)
H_SI  = eta0_H / eta0
```

其中 `eta0_H` 和电场同量级，最适合检查方向、相位和误差。

`H_SI_A_per_m` 是按真空阻抗 `eta0` 换算后的 SI 磁场，单位是 A/m。

## 本阶段的边界

这一步只回答一个问题：

```text
3D 全矢量 Maxwell 主框架能不能在最简单空气盒子里重建一个解析平面波？
```

后续步骤才会增加：

```text
双周期 Floquet
上下 PML
2.5D 拉伸光栅 benchmark
3D 衍射级后处理
3D auxiliary modal port
真实 3D benchmark
```
