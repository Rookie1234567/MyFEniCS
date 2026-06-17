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

## 入射角约定

3D 方向不再直接让用户输入 `(kx, ky, kz)` 或传播向量，而是用两个角度推导：

```text
theta：从向下 -z 方向偏开的角度
phi  ：在 x-y 平面里的方位角
```

传播方向为：

```text
s = (sin(theta) cos(phi), sin(theta) sin(phi), -cos(theta))
```

所以：

```text
theta = 0        -> 正入射，沿 -z 传播
theta > 0, phi=0 -> 朝 +x 方向倾斜
theta > 0, phi=90 -> 朝 +y 方向倾斜
```

偏振目前支持三种：

```text
s      ：垂直于入射平面的线偏振
p      ：位于入射平面内、并且仍然满足 k dot p = 0 的线偏振
custom ：手动给一个偏振向量，代码检查它是否横向
```

Stage 1 的正入射默认用 `custom=(1,0,0)`，这样能直接检查 Ex 平面波。斜入射默认用 `s` 偏振。

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

## 单位和磁场约定

代码内部长度单位统一是微米，所以：

```text
坐标 x,y,z：um
lambda0   ：um
k0        ：1/um
curl      ：按 1/um 求导
```

因此 3D 后处理不再默认输出 SI 单位的 `H[A/m]`。为了和已有 2D 后处理保持一致，代码输出归一化磁场：

```text
H = curl_um(E) / (i*k0*mu_r)
```

这个 `H` 省掉了共同的物理常数，和电场同量级，适合检查方向、相位、Poynting 方向和相对误差。

如果以后要和实验绝对单位或 COMSOL 的 A/m 数值做逐点对比，再单独加一个显式的 SI 换算开关；默认输出保持微米代码单位，避免和 2D 结果口径不一致。

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
