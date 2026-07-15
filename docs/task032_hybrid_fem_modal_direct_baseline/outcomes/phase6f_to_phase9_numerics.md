# Phase 6f--9 数值闭合记录

## 物理场公式与存储

中间区采用 `exp(-i omega t)`，因此 `H=curl(E)/(i k0 mu_r)`；代码再乘冻结的
A/m 缩放。只常驻 z=10/30/60/90/110 nm 的场样本，完整中间 volume 不常驻。
中间吸收使用分段 Gauss-Legendre，局部区仍使用 FEM 体积分。

四条主记录均来自 clean source
`735774473e54415ab5393f2d2cbc9c8d7d2a24e6`、MPI4、complex128 和实际镜像
`sha256:08c61b2cde742442b0031437dbc5160db979494587e6b6364f7935beb29dd76d`。

## h5 模态漏斗

正式 M120->M160 比较为：

```text
max |delta R/T/A| = 6.2395e-14
max significant power relative delta = 2.8783e-10
max significant complex-amplitude relative delta = 1.4793e-10
status = mode_truncation_converged / strong gate pass
```

h5/M160：

```text
R/T/A = 0.0890210691064 / 0.4425867427429 / 0.4683921881508
true residual = 2.5455e-12
volume energy closure = 1.7312e-11
Hybrid-full3D volume A delta = 2.0698e-6
sampled interface E_t max relative L2 = 2.4590e-7
sampled interface H_t max relative L2 = 7.4175e-3
selected-plane E/H max relative L2 = 3.1983e-4 / 9.6141e-4
```

早期宽漏斗中 M20->M40 的 total delta 曾到 `2.25e-5`，所以 M6 的表面稳定
不能替代正式漏斗。M40->M80 只达到 mandatory，M80->M120 和 M120->M160
才形成 strong 平台。

## h3 主单点

h3 基础 3 nm z 轴不含冻结接口 10/110 nm。Hybrid local mesh 插入精确接口，
不移动分区，也不改变 x/y 匹配网格。正式 M120->M160 比较为：

```text
max |delta R/T/A| = 1.2212e-14
max significant power relative delta = 2.6420e-10
max significant complex-amplitude relative delta = 1.3335e-10
status = mode_truncation_converged / strong gate pass
```

h3/M160 主结果：

```text
Hybrid R/T/A = 0.0046128199040 / 0.5836509402052 / 0.4117362398908
Hybrid-full3D delta = -2.1150e-7 / -2.4170e-6 / +2.6285e-6
true residual = 2.6036e-12
sampled interface E_t/H_t max relative L2 = 2.5037e-8 / 4.8169e-4
selected-plane E/H max relative L2 = 9.9644e-5 / 7.7981e-4
volume energy closure = 3.2683e-12
Hybrid-full3D volume A delta = 2.6285e-6
```

这些值通过任务书 `1e-5` 主阈值。h5 与 h3 的 full-3D reference 本身差异大，
所以仍不宣称 h5--h3 网格收敛；这里证明的是各自同网格的 Hybrid/full-3D 对照。

## Modal-Schur

h5/h3 M160 的 augmented 与 Modal-Schur 都满足：modal coefficient、上下局部解、
接口投影、R/T/A 和 full residual 的差异远低于 `1e-9`。Schur 只形成
`320 x 320` dense modal matrix，multi-RHS 数为 `321`；没有 dense
`N_interface^2`，也没有完整 field/mode gather。

## 参数 smoke 边界

正式参数 smoke 为 `30/30 pass`：h5 覆盖 1--10° S/P，h3 覆盖
1/3/5/7/10° S/P。它固定 M=4、candidates=8，只证明参数入口、每点 QEP 重算、
被动方向分类、Hybrid algebra 和衍射输出；不把低 M pointwise field 或整个角度
区间升级为 production qualification。
