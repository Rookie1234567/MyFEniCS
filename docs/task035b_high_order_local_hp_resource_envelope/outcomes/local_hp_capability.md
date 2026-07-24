# Task035b local-hp 能力审计

## 能力矩阵

| capability | 当前状态 | 证据身份 |
|---|---|---|
| same-mesh p4/p5/p6 | pass | actual MPI8 fixed h10 hexa |
| edge/face/interior DoF inventory | pass | measured topology + Basix layout |
| element-interior static condensation | pass, opt-in research path | full residual 与 R/T/A 等价 |
| physically reduced regionwise interior-p | implemented | 两个 actual MPI8 PDE，精度负 |
| exact-sequence structural audit | pass/fail closed | p4/p6 组合 pass；p5-trace/p4-interior fail |
| DWR R00/R/T multi-goal | pass | three independent Hermitian adjoints |
| target p4/p5/p6 smoothness signals | pass with limitations | actual p6 projection on 252 cells |
| classifier v3 | research-qualified | 102 p-up、150 p-keep |
| structured-hexa local-h | architecture unavailable | no hanging-node/transition constraint path |
| tetra selected local-p6 | architecture unavailable | current regionwise implementation is hexa-only |
| production local-hp default | not qualified | ordinary default unchanged |

## Target classifier v3

v3 在同一 canonical h10 hexa mesh 上融合：

- `eta_p4p5/eta_p5p6`；
- strict `DWR_R00/R/T` 与 tolerance-normalized R/T；
- physical `L2+h_K^2 curl` hierarchical shell decay；
- p4/p5 global conforming projection defect；
- material/interface/corner prior；
- 决策前的 x/y periodic transitive component aggregation。

| actual target signal, 252 cells | min | median | max |
|---|---:|---:|---:|
| eta p5p6 / p4p5 | 0.00250 | 0.00561 | 0.02990 |
| physical hierarchical p6/p5 decay | 0.16201 | 0.16289 | 0.16783 |
| coefficient decay，diagnostic only | 0.14644 | 0.14723 | 0.15164 |
| p4 relative projection defect | 0.03436 | 0.03448 | 0.03848 |
| p5 relative projection defect | 0.00655 | 0.00657 | 0.00755 |
| p5/p4 defect decay | 0.18988 | 0.19086 | 0.19644 |

252/252 cells 均解析成功。使用 fast `<=0.35`、slow `>=0.55` 的迟滞区间，
strict-R00 与 normalized-R/T 周期闭合集中的 102 cells 全部为
`p_up_candidate`；其余 150 cells 为 `p_keep_candidate`。没有 measured
target signal 支持 `h_refine_candidate` 或 `p_down_candidate`。

raw coefficient norm 重复计入 shared trace 且不是 orientation-canonical
physical Gram，因此只作诊断，不能覆盖 physical shell/projection 结论。
旧 MPI8 signal record 生成于强化 Gate 之前；v3 已独立重算所有 snapshot
content hash 与四个 energy closure，但旧 record 不含新的 N1E/Piola
contract、p5 round-trip 与 hash-scope 字段。因此 v3 保持
`production_qualified=false`。

## Actual h-vs-p 顺序竞争

现有最可信链是 tetra h50 上：

```text
B: base p5
-> H: one DWR local-h at p5
-> P: frozen refined mesh global p6
```

H 与 P 的 p5 origin 在 mesh/tag hashes、DoF、rows、NNZ 和 observables 上闭合。

| endpoint | cells | DoF / rows | NNZ | R/T/Avolume L2 error | strict-R error |
|---|---:|---:|---:|---:|---:|
| B base p5 | 180 | 15,405 / 15,485 | 3,726,879 | `2.2032e-2` | `1.5130e-3` |
| H one-local-h p5 | 1,248 | 101,210 / 101,290 | 23,913,006 | `6.3581e-4` | `4.3764e-4` |
| P fixed-mesh p6 | 1,248 | 167,784 / 167,864 | 57,609,056 | `1.0224e-4` | `5.1371e-5` |

local-h 的 vector-error log gain/added DoF 更高；p-up 的 strict-R log
gain/added DoF 更高，所以不存在单一 winner。最终 p6 通过 vector control，
但 strict-R control ratio 为 1.421，且 167,784 DoF 超过 90k。

该 record 的 scope 是 `comparable_sequential_global_marginal_proxy`：
`head_to_head_same_origin=false / same_patch=false /
cell_decision_authority=false`。它不能清除同 patch local h/p competition 缺口。

## C4 fault fixtures

| fixture | 期望与结果 | evidence class |
|---|---|---|
| smooth analytic N1curl | fast shell/defect decay -> p-up | synthetic method fixture |
| aligned Hcurl-normal material jump | unresolved -> moderate p-keep，不凭 prior 造 h | synthetic method fixture |
| interface low regularity | slow physical decay -> h candidate | synthetic method fixture |
| corner low regularity | physical slow；coefficient fast 不得否决 | synthetic method fixture |
| under-resolved `sin(4πx)` | resolution Gate -> undetermined | synthetic method fixture |
| periodic transitive mates | worst signal/goal OR 后统一 action | synthetic method fixture |
| MPI2 rank-local invalid input | collective fail-fast，无 hang | synthetic method fixture |

所有 fixture 都是 `target_physics_evidence=false`。特别是 p6 离散投影不能
排除所有高频 alias；目标网格尚无独立 phase-resolution authority。

## Lane B 受控停止

structured hexa backend 没有 hanging-node/transition-cell conformity，不能在
当前目标 mesh 上做一次真实 local-h；现有 periodic tetra 能做 local-h，但
当前 physically reduced selected-p6 与 assembly-time Schur 只支持 hexa。
此外已有 h50/h37.5 tetra 证据表明 refined p5 已在 101k–129k DoF，selected
p6 架构缺失，继续重复 h40/h35 或更多 p6 不会解除 90k 与 exact-conformity
Gate。

因此

```text
p5 + one local-h + selected p6 =
stopped_by_gate_architecture_and_budget
```

这不是 solver 失败，也不是 local-h 数学上无效；它只是当前代码架构和预算下
没有可执行、可同误差资格化的组合。历史 Task035 heavy references 不重复运行。

