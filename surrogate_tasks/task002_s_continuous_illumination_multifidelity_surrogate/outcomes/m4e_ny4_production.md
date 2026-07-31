# Task002 M4E：Ny4 production rebaseline 与 112 点 campaign

## 1. 结论

Review V7 Required M4E 已完成。`_mode_projection_from_solution` 现在只投影
切向电场 `(Ex,Ey,0)` 与切向 mode vector，不再把 `Ez` 放入分子。Task002
唯一 production route 已冻结为 Full3D static uniform N1curl p5/h10/MPI2，
runtime axis counts 为 `(6,4,14)`。

增强 canary 全部通过后，Case119 从头生成了 96 个 training 与 16 个 frozen
validation 样本，112/112 均为 `measured_pass`。Case117 保持不可变，原 Ny3 的
56 个 pass 没有进入新 campaign 或 dataset。

## 2. Production 身份

| 项目 | 冻结值 |
|---|---|
| implementation baseline | `10e3356ba8364286a452077f71d7e3b92ea24cd5` |
| model_id | `S_PROD_FULL3D_STATIC_P5_H10_NY4` |
| solver_route_id | `full3d_static_uniform_n1curl_p5_h10_ny4` |
| mesh | `(Nx,Ny,Nz)=(6,4,14)` |
| parameter schema | `task002.s-p5-ny4-production-parameters.v3` |
| observable schema | `task002.fixed-n0-orders.v3` |
| campaign schema | `task002.s-p5-ny4-design-campaign.v4` |
| dataset schema | `task002.s-p5-ny4-single-fidelity-dataset.v3` |

主工作树在 baseline 后只增加了报告和用户授权的历史文档合并。恢复 campaign 时使用
隔离的 clean baseline clone；其 origin、branch、upstream、HEAD、ABI 和资源预检均满足
正式 provenance 合同。每个 formal record 继续绑定上述 implementation SHA。

## 3. Tangential projection 修复

测试覆盖 oblique S、含非零 `Ez` 的 P、lossy-bottom P 和 top incident subtraction。
独立 q63 direct tangential projection 对所有实际 power-carrying S/P modes 的最大差异为：

| 诊断点 | 最大绝对差 |
|---|---:|
| 原失败几何 Ny3（诊断、仍隔离） | `1.923e-13` |
| 原失败几何 Ny4 | `1.094e-12` |
| 中心几何 54.50° Ny4 | `4.814e-13` |
| 10° grazing / 45° azimuth Ny4 | `9.108e-14` |

全部低于 `1e-10` Gate。Ny3 仅用于合同回归，其 leakage 仍失败，因此没有获得
production 身份。

## 4. 冻结设计 rebind

只更新 source/model/route/topology/schema/combined metadata，四元组点表未改变：

| 设计 | tuple SHA-256 |
|---|---|
| training 96 | `b01f4f3b27b5b5e0466fb1d620ffe504677f6c24468ac9e955ac45fac39570fa` |
| frozen validation 16 | `e5733173c2c55d4d5ef8e660fc63019bf61e78063a3bd24cb0488dc6c435e50b` |
| candidate pool 4096 | `a9831ffc1055732660bee859382f623e8558560634d9ac98702cfe355ff09fcd` |
| discretization audit 8 | `049b973bbed7de05e46e8045fac11461ac80641f08aa464bb81d7aa72611a2aa` |

新的 combined design SHA-256 为
`815cc12aa2fe8a79c87f72fb548e516f45ae0ff7640454075dd13b1c32344105`。

## 5. Enhanced canary

- 16/16 domain corners：全部 formal Gate 通过；
- 原 training index 40：总 n!=0 power 为 `3.2783e-25`，最大复振幅
  `2.3532e-13`；
- 中心几何 54.25°/54.50°/54.75°：总泄漏分别为
  `9.765e-26`、`4.860e-26`、`3.783e-26`；
- 三点最大复振幅分别为 `1.881e-13`、`7.707e-14`、`3.847e-14`；
- residual、energy closure、fixed/raw ledger、Ny4 runtime topology、uniform
  N1curl p5、zero swap、cleanup 和 compact output identity 全部通过。

## 6. Campaign inventory 与资源

| split | expected | measured_pass | failure |
|---|---:|---:|---:|
| training | 96 | 96 | 0 |
| frozen validation | 16 | 16 | 0 |
| total | 112 | 112 | 0 |

最终 112 个 production attempts 全部 zero swap、cleanup complete；所有正式样本
来自一个 clean SHA、一个 Ny4 model/route 和 observable v3。包括一次用户请求暂停在内，
manifest 共保留 113 次 attempt：training index 4 attempt 1 为
`interrupted_retryable`（signal 143、zero swap、cleanup complete、无 formal record），
attempt 2 从头计算并通过。它不是 numerical failure，也没有进入 dataset。

全 campaign 峰值 RSS 为 `6,209,052,672` bytes，峰值 PSS 为
`6,004,024,320` bytes。没有 skipped failure。8 个 discretization-audit points 未运行，
并继续独立于 production dataset。

## 7. 边界

frozen-validation 响应只运行和封存，没有用于 feature、kernel 或模型选择。本轮没有
开始 PCE、GP、validation scoring、active learning、angle DOE 或 inversion。
