# Phase 6f--9 数值闭合记录

## 物理场公式与存储

中间区采用 `exp(-i omega t)`，因此 `H=curl(E)/(i k0 mu_r)`；代码再乘冻结的
A/m 缩放。只重构 z=10/30/60/90/110 nm，完整中间 volume 不常驻。中间吸收
用分段 Gauss-Legendre，局部区仍用 FEM 体积分。

## h5 模态漏斗

```text
M = 20 -> 40 -> 80 -> 120 -> 160
selected/candidate at final = 160/320 per target branch
M120 -> M160 max |delta R/T/A| = 7.7105e-14
max significant complex order relative delta = 2.2161e-10
interface weak projection residual = 3.9122e-13
status = strong truncation convergence
```

h5/M160：

```text
R/T/A = 0.0890210691063 / 0.4425867427429 / 0.4683921881507
volume energy closure = 1.7423e-11
Hybrid-full3D volume A delta = 2.0698e-6
sampled interface E_t max relative L2 = 2.4590e-7
sampled interface H_t max relative L2 = 7.4175e-3
middle-plane E/H max relative L2 = 2.8800e-4 / 8.7917e-4
```

M40 相对 M20 的 total delta 曾到 `2.25e-5`，所以早期 M6 的表面稳定不能替代
宽漏斗。M40->M80 达到 mandatory 但未达到 strong；M80->M120 和
M120->M160 才形成强收敛平台。

## h3 主单点

h3 的基础 3 nm z 轴不含冻结接口 10/110 nm。Hybrid local mesh 插入精确接口，
不移动分区，也不改变 x/y 匹配网格。M120 和 M160 均执行 augmented 与
Modal-Schur 对照；M120->M160 结果：

```text
max |delta R/T/A| = 3.5527e-14
max significant complex order relative delta = 9.8615e-11
status = strong truncation convergence
```

h3/M160 主结果：

```text
Hybrid R/T/A = 0.0046128199040 / 0.5836509402052 / 0.4117362398908
Hybrid-full3D delta = -2.1150e-7 / -2.4170e-6 / +2.6285e-6
true residual = about 2.3e-12
interface weak projection residual = about 4.2e-13
sampled interface E_t/H_t max relative L2 = 1.0394e-7 / 4.8169e-4
middle-plane E/H max relative L2 = 4.3549e-5 / 7.7981e-4
Hybrid-full3D volume A delta = 2.6285e-6
```

以上均通过任务书 `1e-5` 主阈值。h5 和 h3 的 full-3D reference 本身差异大，
仍不宣称 h5--h3 full-3D 网格收敛；这里证明的是各自同网格 Hybrid 对照。

## Modal-Schur

两档 M160 均满足：modal coefficient、上下局部解、接口投影和 R/T/A 与
augmented 的差异远低于 `1e-9`；Schur full residual 通过，且只形成
`2M x 2M` dense matrix。multi-RHS 数为 `2M+1`，未形成 dense
`N_interface^2`，也未聚集完整 field/mode。

## 参数 smoke 边界

参数 smoke 固定较小 M，只证明角度/偏振入口、每点 QEP 重算、被动方向分类、
Hybrid residual 和衍射输出正确；不把低 M 的 pointwise field Gate 或整个
1--10° 范围升级为 production qualification。
