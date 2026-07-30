# Task002 M4D：y 向离散 Bragg / trace alias 诊断

## 1. 结论

Case117 的第一个失败不是随机求解波动，也不是 surface quadrature 不足。
根因已被定量确认为：`Ny=3` 时，实际有限元端口 trace space 把物理上应正交的
`n=0` 与 `n=-3` 模式显著混合；在 `2ky ≈ 3Gy` 的窄角度区间，这个离散
Bragg/alias 对被放大。

只把 y 向单元数从 3 改成 4，泄漏从 `1.2312e-6` 降到 `3.2783e-25`，
实际 trace-vector overlap 从 `0.3630` 降到 `2.68e-16`。Ny=5/6 保持舍入误差
量级。因此 Route A（Ny=4）得到支持，但本轮没有修改 production mesh，也没有
恢复 M4。Review V7 前仍禁止 Case117 bulk、validation 和代理训练。

独立 `E_total` 高阶投影还暴露了第二个、与 y-alias 不同的问题：S amplitude
与 auxiliary unknown 一致到约 `7.7e-14`，但 P amplitude 最大差异约
`5.25e-3`。Task002 是 S 入射，但 observable/Gate 同时保存 outgoing S/P；这个
P 不一致被保留为负证据，必须由 Review V7 disposition，不能静默忽略。

## 2. 身份与执行边界

| 项目 | 值 | 数据身份 | 证据 |
|---|---:|---|---|
| clean M4D SHA | `0a53c42397a2e67f64e8f6dae2c680bfe3fe4b95` | measured provenance | Case118 records |
| 求解器 | Full3D static uniform N1curl p5/h10/MPI2 | measured | Case118 config |
| 固定规模 | Nx=6, Nz=14, p=5 | measured | runtime topology |
| 正式泄漏 Gate | power ≤ `1e-7`; amplitude ≤ `1e-4` | frozen | Case118 expected |
| 角度扫描 | 失败几何 14 点 + 中心几何 14 点 | measured | `azimuth_resonance_map.json` |
| Ny 矩阵 | 3/4/5/6 | measured | `y_cell_convergence.json` |
| surface q 矩阵 | auto=21/31/39/47 | measured | `surface_quadrature_convergence.json` |
| Case117 bulk | 未恢复 | not_run | solver route decision |
| training 41–95 / frozen validation | 未运行、未读取 | not_run | solver route decision |

所有 35 个新 PDE（失败点复现 1、两套角度扫描 28、额外 Ny 3、额外 q 3）均
direct solve 完成、zero swap、watchdog cleanup complete。Case117 raw evidence 与冻结
四元组点表没有改动。

## 3. 失败邻域峰值图

固定 `grazing=4.538499870338°`。下表列出近峰核心；完整 50–58° 点表同时保存
`ky`、`2ky-3Gy`、n=0/n=-3 的 alpha/gamma/beta、auxiliary amplitude/power、
R/T/A、residual、ledger 和 q。

| 几何 | azimuth (°) | `2ky-3Gy` (nm⁻¹) | n≠0 power | max boundary amplitude | 判定 |
|---|---:|---:|---:|---:|---|
| failed | 54.00 | -3.2763e-3 | 4.1919e-11 | 1.8537e-6 | power pass, amplitude pass |
| failed | 54.25 | -9.0366e-4 | 1.1078e-6 | 1.2424e-3 | fail |
| failed | 54.50 | 1.4547e-3 | 8.9071e-7 | 8.2708e-4 | fail |
| failed | 54.75 | 3.7987e-3 | 1.9963e-7 | 3.3475e-4 | fail |
| center | 54.00 | -3.2763e-3 | 2.0268e-11 | 1.1547e-6 | pass |
| center | 54.25 | -9.0366e-4 | 1.1038e-6 | 1.2436e-3 | fail |
| center | 54.50 | 1.4547e-3 | 8.8871e-7 | 8.2713e-4 | fail |
| center | 54.75 | 3.7987e-3 | 1.9873e-7 | 3.3445e-4 | fail |

两套几何的峰位和峰高几乎相同：这是角度/离散结构主导，不是原 Sobol 几何的
特殊放大。原精确失败角 `54.420819°` 位于 54.25° 与 54.5°之间，复现值为
`1.2312320314e-6`，与 Case117 完全一致。

## 4. Ny 收敛和 n=0 aggregates

| Ny | n≠0 power | max amp | R | T | A_balance | bottom-S overlap | Gram cond | PSS (GB) | swap |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 1.2312e-6 | 1.0147e-3 | 0.00650900 | 0.29609606 | 0.69739494 | 3.6302e-1 | 2.1398 | 4.16 | 0 |
| 4 | 3.2783e-25 | 2.3532e-13 | 0.00644595 | 0.29623235 | 0.69732170 | 2.6829e-16 | 1.0000 | 5.82 | 0 |
| 5 | 1.1317e-24 | 1.6618e-13 | 0.00644227 | 0.29624034 | 0.69731739 | 1.4648e-16 | 1.0000 | 7.87 | 0 |
| 6 | 5.8333e-25 | 1.8991e-13 | 0.00644188 | 0.29624118 | 0.69731693 | 1.1292e-16 | 1.0000 | 10.60 | 0 |

Ny=4 相对 Ny=6 的 `|ΔR|=4.07e-6`、`|ΔT|=8.83e-6`；Ny=5 相对 Ny=6
进一步降到 `3.88e-7` 与 `8.43e-7`。因此 Ny=4 不只是消除泄漏，n=0 aggregates
也沿 Ny refinement 稳定收敛。Ny=6 仍低于本机资源上限且 zero swap，但生产候选
优先选择成本较低、已消除 alias 的 Ny=4。

demodulated `E_total * exp(-i ky y)` 的 bottom-port `n=-3` Fourier energy fraction
由 Ny=3 的 `3.10e-6` 降到 Ny=4 的 `4.88e-26`，与端口功率和 Gram 证据一致。

## 5. Surface quadrature 与独立投影

| surface q | n≠0 power | max boundary amplitude | 结论 |
|---:|---:|---:|---|
| auto=21 | 1.2312320314e-6 | 1.0146566168e-3 | fail |
| 31 | 1.2312320314e-6 | 1.0146566168e-3 | fail |
| 39 | 1.2312320314e-6 | 1.0146566168e-3 | fail |
| 47 | 1.2312320314e-6 | 1.0146566168e-3 | fail |

四个 q 的结果逐位相同，排除 Fourier surface assembly 的欠积分。actual-trace Gram
overlap 对 q 也不变，说明 alias 来自 Ny=3 trace 表示本身。

q63 独立边界投影显示：

- outgoing S：auxiliary 与 `E_total` direct projection 最大差异 `7.69e-14`；
- outgoing P：最大差异 `5.25e-3`（Ny=3）、`1.84e-3`（Ny=4），未随 alias 消失。

因此 S 泄漏确实存在于离散 FE/DtN 解本身，不是仅有 auxiliary extractor 错标；P
不一致是另一个待处理的 auxiliary/recovery/projection 合同问题。

## 6. Route 决策

| Route | 本轮判定 | 理由 |
|---|---|---|
| A：Ny=4 | supported candidate | 原失败点全部既有 Gate 通过；alias、Gram overlap 降至 roundoff；n=0 aggregates 收敛 |
| B：quadrature bug | rejected as primary cause | q21–47 完全不变 |
| C：近退化 port basis | Ny=3 mechanism confirmed, refinement resolves | Ny=3 overlap O(1)，Ny≥4 正交恢复；暂不需要 block orthogonalization |
| D：放宽 Gate | forbidden / unnecessary | Ny=4 在原阈值下通过 |

本轮没有把 `AXIS_CELL_COUNTS` 改成 `(6,4,14)`，也没有 rebind design 或运行新
canary。这些属于 Review V7 是否批准 Route A 后的新 production SHA 工作。可选的
standard-full/static-condensed A/B 没有运行：Ny-only A/B 已在固定 backend 下把
overlap 从 O(1) 降到 roundoff，且独立投影发现新的 P discrepancy；在 Review V7
disposition 前没有额外启动未资格化的高内存 standard-full p5。

## 7. 证据索引

- `benchmarks/cases/118_task002_y_alias_qualification/records/failed_point_reproduction.json`
- `benchmarks/cases/118_task002_y_alias_qualification/records/azimuth_resonance_map.json`
- `benchmarks/cases/118_task002_y_alias_qualification/records/y_cell_convergence.json`
- `benchmarks/cases/118_task002_y_alias_qualification/records/surface_quadrature_convergence.json`
- `benchmarks/cases/118_task002_y_alias_qualification/records/auxiliary_vs_direct_projection.json`
- `benchmarks/cases/118_task002_y_alias_qualification/records/port_vector_gram_condition.json`
- `benchmarks/cases/118_task002_y_alias_qualification/records/solver_route_decision.json`
- `benchmarks/cases/118_task002_y_alias_qualification/records/case118_check.json`
