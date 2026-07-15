# Task032：0.7 nm 可扩展性评估

## 1. 判定

| 问题 | 判定 | 数据身份 | 证据 / 限定 |
|---|---|---|---|
| 13.5 nm Hybrid 域分解是否正确 | yes | measured | h5/h3 与同网格 full3D 的 R/T/A、场、吸收通过 |
| 当前 direct Hybrid 能否用于 0.7 nm | no | analytical projection | 当前 local LU、显式模态和 all-mode RHS 失控 |
| 1 TiB 是否绝对不可能 | no | engineering decision | 存在 conditional opportunity，但尚未证明 |
| 可信主线 | exact complex 3D ends + generic modal middle | architecture decision | addendum 修正后的长期目标 |
| 必要条件 | h/p + scalable modal core + low-storage iterative | design Gate | 三项必须同时成立 |
| pure-modal / y-invariant | optional current-geometry diagnostic only | scope decision | 不进入未来服务 Gate 或资源预算 |

本报告不运行 PDE，也不把解析外推计入 solver pass。配套
[`task032_0p7nm_projection.json`](task032_0p7nm_projection.json) 的唯一身份是
`analytical_resource_projection`。

## 2. 当前 13.5 nm 实测事实

| mesh / method | FE/local rows identity | ext. aux | internal modal | total rows | assembled NNZ | worker RSS | 数据身份 / 证据 |
|---|---:|---:|---:|---:|---:|---:|---|
| h5 full3D | 44,698 Nédélec | 80 | 0 | 44,778 | 4,896,156 | historical sampler only | measured full3D record |
| h5 Hybrid M160 | 6,866 + 6,866 local rows | included | 320 | 14,052 | 2,000,624 | 1.698 GiB minimal | measured M160 + memory record |
| h3 full3D | 198,438 Nédélec | 80 | 0 | 198,518 | 21,317,860 | historical sampler only | measured full3D record |
| h3 Hybrid M160 | 34,238 + 34,238 local rows | included | 320 | 68,796 | 8,594,673 | 3.224 GiB minimal | measured M160 + memory record |

| mesh | rows reduction（分母=full3D） | NNZ reduction（分母=full3D） | max same-grid `|ΔR/T/A|` | 数据身份 |
|---|---:|---:|---:|---|
| h5 | 68.62% | 59.14% | `2.07e-6` | derived reduction + measured error |
| h3 | 65.35% | 59.68% | `2.63e-6` | derived reduction + measured error |

Hybrid 已产生真实代数降维，不只是概念上的域缩短。但 full3D 与 Hybrid 的内存记录不是同一
simultaneous sampler，不能据此计算精确 full3D→Hybrid RSS 百分比。

## 3. M 的含义与模式数情景

`M` 是中间二维截面在**每个传播方向**保留的 Maxwell 本征模数，包含传播模和表示接口近场所需的
衰减模。M160 代表 160 forward + 160 backward = 320 internal amplitudes。

generic `epsilon(x,y)` 的传播 reciprocal-order 估算为：

$$N_{order}\approx\pi L_xL_y/\lambda^2,\qquad
M_{prop}\approx2\pi L_xL_y/\lambda^2.$$

| wavelength | generic reciprocal orders | two-pol modes / direction lower bound | current M160 / lower-bound ratio at 13.5 | 数据身份 |
|---:|---:|---:|---:|---|
| 13.5 nm | 21.5 | 43.1 | 3.71x | analytical geometry count |
| 5 nm | 157.1 | 314.2 | not applied | analytical geometry count |
| 2 nm | 981.7 | 1,963.5 | not applied | analytical geometry count |
| 1 nm | 3,927.0 | 7,854.0 | not applied | analytical geometry count |
| 0.7 nm | 8,014.3 | 16,028.5 | not applied | analytical geometry count |

| 0.7 nm 情景 | M / direction | 身份 | 是否用于服务预算 | 解释 |
|---|---:|---|---|---|
| generic propagation lower bound | 16,029 | analytical lower bound | yes, as floor only | 未含 evanescent buffer |
| mechanical 3.7x carry-over | 59,306 | risk illustration | no, not a prediction | 只暴露 current layout 数量级 |
| current y-invariant two-pol diagnostic | about 286 | optional diagnostic | **no** | Case080 简单几何特例 |

未来中间区只冻结为 `epsilon(x,y,z)=epsilon(x,y)`，所以 generic 2D QEP 必须保留。y-sector 或
pure-modal 可以帮助检查当前规则 benchmark，但不能成为复杂服务路线的强制 Gate。

## 4. 当前对象复杂度与重构要求

| 对象 | 当前复杂度 / ownership | h3/M160 measured scale | 0.7 nm 风险 | required redesign |
|---|---|---:|---|---|
| right/left full/reduced modes | `O(Nxy M)`，多份并存 | 40,929,280 bytes | TB 级 | streamed/compressed，保留必要 trace |
| projection/traction | `O(Ninterface M)` | 207,360 / 233,280 NNZ | 大通信/存储 | distributed blocked action |
| biorthogonality/negative map | replicated `O(M²)` | 160² | 单 rank dense bottleneck | block/distributed/no global replica |
| modal Schur/constraint | replicated `(2M)²` | 1,638,400 bytes | tens–hundreds GiB per copy | matrix-free/distributed apply |
| local multi-RHS | `Nlocal x (2M+1)` | 321 RHS | projected dominant wall | block/streamed RHS |
| modal owner | all modal rows on final rank | M160 | imbalance/concentration | distributed modal ownership |
| QEP | shift-invert MUMPS, about 2M candidates | h3 full 2,053 | thousands of pairs | spectrum slicing/continuation |
| local FEM | MUMPS direct LU | 30.59M / 30.08M factor NNZ | impossible at 1e9 rows | matrix-free low-memory iterative |

## 5. 确定性 0.7 nm 投影

输入冻结为 `lambda=0.7 nm, Lx=50 nm, Ly=25 nm, local thickness=20 nm,
h=0.1 nm, safety factor=3.7, MPI=4`。脚本：
[`benchmarks/run_task032_scalability_projection.py`](../../../benchmarks/run_task032_scalability_projection.py)。

| 输出量 | 值 | 单位 | 数据身份 | 公式 / 限定 |
|---|---:|---|---|---|
| generic propagation lower bound | 16,028.53 | modes/direction | derived | `2πLxLy/lambda²` |
| illustrative retained M | 59,306 | modes/direction | predicted illustration | lower bound ×3.7；非 converged M |
| internal amplitudes | 118,612 | unknowns | derived | `2M` |
| QEP full DoF | 1,847,700 | DoF | predicted | h3 2,053 × `(3/0.1)²` |
| local FE rows | 923,346,000 | rows | predicted | 68,396 × `(3/0.1)³` ×20/40；external aux not projected |
| local-system row mechanical proxy | 924,426,000 | rows | predicted | baseline includes 80 aux and mechanically scales them；payload proxy only |
| one complex `(2M)²` | 225,100,904,704 | bytes | derived | complex128 |
| four replicated squares, MPI4 total | 3,601,614,475,264 | bytes | predicted layout | 4 arrays ×4 ranks |
| right/left eigenvector payload | 13,653,854,323,200 | bytes | predicted layout | current h3 payload mechanical scale |
| all-mode dense multi-RHS | 1,754,383,058,208,000 | bytes | predicted layout | `Nlocal(2M+1)×16` |
| largest single explicit object | 1,595.60 | TiB | predicted layout | all-mode RHS/solution proxy；**excludes** factors、mesh、Krylov |
| cumulative explicit-object volume | 1,611.30 | TiB | predicted layout | objects need not coexist；not a simultaneous process peak |

1,595.60 TiB 是 current layout 最大单对象的机械 payload proxy；1,611.30 TiB 是多对象累计体积，
不是同时峰值。二者都不是未来优化实现的 RSS 预测，而是“把现有参数机械放大”不可行的反证。

## 6. local 3D DoF 预算

| local geometry / grid | estimated rows | 数据身份 | 1 TiB judgment |
|---|---:|---|---|
| current 40 nm, uniform h0.1 | about 1.85e9 | predicted | no |
| future 20 nm, uniform h0.1 | about 9.23e8 FE rows | predicted | no |
| adaptive target `<=2e8` | design Gate | target | relatively promising |
| adaptive `2e8–3.5e8` | design Gate | candidate | credible candidate zone |
| adaptive `3.5e8–5e8` | design Gate | high risk | only with measured margin |
| adaptive `>5e8` | design Gate | likely infeasible | stop before full solve |

Task033 必须在 13.5 nm direct reference 上证明同等误差时至少 3x、优选 5x local DoF reduction。
这不是保证 0.7 nm 可解，而是进入下一阶段的必要条件。

## 7. 1 TiB 与 2 TiB 内存预算

| component | 1 TiB design budget | 2 TiB design budget | 数据身份 | 说明 |
|---|---:|---:|---|---|
| OS/MPI/runtime/allocator | 80–120 GiB | 120–200 GiB | design budget | 不可借给 solver 峰值 |
| mesh/DoF/coefficient/geometry | 80–180 GiB | 150–320 GiB | design budget | 必须分布式 |
| Krylov/solution/work vectors | 100–220 GiB | 180–400 GiB | design budget | low restart / low storage |
| matrix-free multilevel/Schwarz | 200–350 GiB | 350–700 GiB | design budget | no global fine matrix/LU |
| distributed/streamed modal core | 100–250 GiB | 180–500 GiB | design budget | no replicated M² |
| safety margin | 80–150 GiB | 150–300 GiB | design budget | 必须保留 |

各组件区间是条件 envelope，不能同时取各列上限；具体设计中各项分配和必须不超过 1 TiB / 2 TiB
总预算，并保留表内 safety margin。

| effective whole-solver memory | 200M FE DoF | 300M FE DoF | 500M FE DoF | 判定 |
|---|---:|---:|---:|---|
| 2 kB/DoF | 372.5 GiB | 558.8 GiB | 931.3 GiB | preferred ceiling；500M 已无 modal margin |
| 3 kB/DoF | 558.8 GiB | 838.2 GiB | 1,397.0 GiB | hard exploratory ceiling；300M 已很紧 |

1 TiB 的结论是 `credible conditional opportunity, not demonstrated`。2 TiB 增加余量，但不会修复
复制 M²、all-mode RHS 或十亿 DoF local LU 的算法复杂度。

## 8. 路线比较

| 路线 | complex 3D ends | generic epsilon(x,y) | 0.7 nm 角色 | 决定 |
|---|---|---|---|---|
| current Task032 direct Hybrid | yes | yes | 13.5 nm reference only | retain, not production scalable |
| final Hybrid h/p + iterative | yes | yes | main target | retained conditional route |
| pure-modal/EME | no local 3D | current simple geometry only | optional independent reference | not mandatory |
| y-invariant sector path | may simplify benchmark | no generic guarantee | optional diagnostic | excluded from service budget |
| uniform full3D FEM | yes, whole domain | n/a | fallback reference at small scale | not 0.7 main route |
| approximate/multifidelity | model-dependent | model-dependent | inversion acceleration after reference | cannot replace Maxwell reference now |

## 9. 波长缩短前的硬 Gate

| 顺序 | Gate | required evidence | fail action |
|---:|---|---|---|
| 1 | Task033 local DoF reduction `>=3x`（preferred 5x） | 13.5 nm same-error R/T/A/field + DoF table | stop interface/hp design |
| 2 | Task034 no replicated M² / no all-mode RHS | ownership/payload ledger + MPI tests | stop modal scale-up |
| 3 | generic QEP/adaptive M converges | R/T/A、amplitude、interface residual funnel | do not infer M from geometry only |
| 4 | Task035 `<=2 kB/DoF` preferred，`<=3 kB/DoF` hard ceiling | simultaneous RSS + object ledger | stop large solve |
| 5 | full explicit true residual + interface continuity | independent Gate | no official R/T/A |
| 6 | each wavelength resource projection fits | 13.5→5→2→1→0.7 update | fail closed at current wavelength |
| 7 | material dispersion updated | same source/schema | no stale 13.5 nm index at 0.7 |

## 10. 修正后的路线

| Task | 工作 | 成功条件 |
|---|---|---|
| 033 | local h/p adaptivity + interface-budget optimization | 3x minimum / 5x preferred DoF reduction at 13.5 nm |
| 034 | scalable generic 2D modal core | distributed/streamed/adaptive；no replicated M²/all-mode RHS |
| 035 | final Hybrid iterative | matrix-free local FEM + low-memory H(curl) + scalable modal action |
| 036 | wavelength continuation | 13.5→5→2→1→0.7，逐步资源/数值 Gate |

未来底端和顶端的精确 complex 3D Nédélec FEM 是必要能力。Review V1 原第 6、7 节以及第 12 节
pure-modal-first 建议已被 addendum 明确 supersede，本报告不再把它们当主路线。
