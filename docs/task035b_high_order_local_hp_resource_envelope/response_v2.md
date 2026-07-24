# Task035b Response V2：显著通道定向恢复批次

## 1. 身份、范围与最终结论

```text
execution_branch = codex/20260723-task35b-high-order-local-hp-resource-envelope
review_v1_commit = a0081afac258480b31fbfc3e94c358fa39d2eacd
evidence_through_head = 0851b14f83f724f7102444277c176caf09e15bf6
final_delivery_head = <TO_BE_FILLED_BY_MAIN_AGENT_AFTER_FINAL_COMMIT>
geometry_scope = Task034 fixed rectangular block grating only
formal_MPI = 8
final_status = PARTIAL_WITH_CONTROLLED_NEGATIVES
hybrid_eligible_candidate_count = 0
selected_candidate = null
ordinary_default_changed = false
master_merge = not_authorized
irregular_geometry = out_of_scope_by_user / not_run / not_a_completion_gate
user_action_hard_blocker = false
```

本轮完成了 Review V1 授权的 reference v1、16 个失败通道独立
Hermitian adjoint、mesh/topology-resolution、phase、trace 与 DtN/port
根因假设判别、方向性 structured-h 恢复和多个轻量并行判别。最强预算内点为：

```text
fixed p5-trace/p6-interior h13 directional-z
axis plan = (6, 2, 12)
Full3D-equivalent DoF = 89,740
active rows = 20,120
matrix/factor NNZ = 11,013,212 / 36,273,200
process-tree peak = 6.41059 GiB
significant power = 10/12
significant complex amplitude = 10/12
```

它仍未达到强制的 `12/12 + 12/12`，因此是具有正恢复信号的
`controlled negative`，不是 same-error 成功候选。没有触发 Hybrid、
M funnel、external DtN funnel 或 0.7 nm / 2 TiB resource model v3。

### 1.1 Review V1 逐项处置

| Review V1 项目 | evidence semantics | 处置 |
|---|---|---|
| CR0 significant channel reference v1 | `measured + mechanically aggregated` | 完成；12/12 均冻结，11 个严格 p/h 单调，1 个 bounded-final-h |
| CR1 六个 power + 十个 amplitude-component adjoint | `measured` | 16/16 独立 Hermitian adjoint 验证通过 |
| CR1 cell/face/edge localization | `derived proxy` | 已保存 recovered-dual coefficient proxy；**不是 DWR** |
| CR1 actual residual-weighted DWR | `not_run_by_capability_gate` | 缺少 global-p6-trace enriched residual/operator，未伪称 DWR |
| CR2 mesh/phase 假设 | `measured + diagnostic` | z-only 明确正信号；fixed-trace x control 为负；global-p5 y mechanism control 无 material response，但不是 same-space y 排除 |
| CR2 trace 假设 | `measured discriminator` | same-mesh full-p6-trace marginal 为正，但超 DoF 上限且仍为 9/12 power；不授权 selective subset |
| CR2 DtN/port 假设 | `measured + manufactured authority` | 已测试 q31、scaled buffer1 均无 material recovery；没有覆盖完整 external DtN funnel |
| Lane A directional structured-h | `measured` | h14、h13 z 正信号；h13 最强但仍 10/12 + 10/12 |
| Lane B selective p6 trace | `capability_stop_not_run` | 无合法 subset、无候选、无 PDE |
| Lane C minimal combination | `not_run_by_lane_gate` | 没有可执行 Lane B；response-matrix 也没有支持的组合 |
| p7 判别点 | `controlled_stop_before_PDE` | end-to-end capability 不足且 projected DoF 为 273,581 |
| condensed iterative prototype | `capability_stop_not_run` | 缺 dedicated factor-free profile/provenance；没有 raw-option 冒充结果 |
| inversion-aware observable selection | `not_run` | 真实参数、噪声和测量集合尚未冻结；12 通道 Gate 保持不变 |
| Hybrid / M / external DtN | `not_run_by_selected_candidate_gate` | 未触发 |
| resource model v3 | `not_run_by_hybrid_gate` | 未触发；production feasibility 仍为 `unknown` |

## 2. Significant channel reference v1

### 2.1 冻结身份

| item | value |
|---|---|
| record | [`significant_channel_reference_v1.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json) |
| record SHA256 | `83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3` |
| authority-manifest SHA256 | `c8538133617ffbeffb1de2f18f8a7134082018f9f85d6a50ea72e0e83ff718b2` |
| reference-payload SHA256 | `bb78f17a0eb3a664620b9acf7cad47dd75c1881899cf885cc243328e320177ba` |
| significant selection | p6/h10 authority，power floor `1e-8`，12 channels |
| center | FEniCS global p6/h10 best-available same-code discrete reference |
| convergence status | 12/12 `reference_converged` |
| strict p/h monotone | 11/12 |
| bounded-final-h confirmation | 1/12：`R(-7,0)_s` |
| acceptance Gate | 原 v0 h10 p5-to-p6 absolute correction；未放宽 |
| `canonical` / `production_qualified` | `false / false` |

reference v1 机械聚合了 `p4/h10`、`p4/h7.5`、`p4/h5`、
`p5/h10` 和 `p6/h10`。`p5/h15`、`p6/h15` 与 fixed-trace h15
只作为 underresolved diagnostics，未进入 numerical band，也未改变原
v0 接受阈值。reference v1 是冻结的研究 reference，不是 continuum truth。

### 2.2 十二通道中心与收敛状态

复振幅均为 boundary-reference outgoing amplitude，格式为
`real + imag i`。

| channel | reference power | reference complex amplitude | p direction | h direction | reference status |
|---|---:|---:|---|---|---|
| T(-7,0) s | `2.36201044924e-6` | `9.81221050834e-4 - 8.72374996020e-5 i` | stable | strict monotone | converged |
| T(-5,0) s | `2.11920825720e-7` | `1.34032696607e-4 + 1.47005784286e-4 i` | stable | strict monotone | converged |
| T(-4,0) s | `4.37288897207e-7` | `-2.62132207531e-4 + 8.74322690375e-5 i` | stable | strict monotone | converged |
| T(-2,0) s | `2.95984139513e-6` | `-6.97002780558e-4 + 2.97942080721e-4 i` | stable | strict monotone | converged |
| T(-1,0) s | `2.17816739855e-5` | `2.09101338530e-3 - 1.02337986284e-3 i` | stable | strict monotone | converged |
| T(0,0) s | `6.02673872347e-1` | `6.31378703348e-1 + 4.73020981038e-1 i` | stable | strict monotone | converged |
| R(-7,0) s | `6.26354242222e-7` | `-5.05209111247e-4 - 2.60888617007e-5 i` | stable | bounded final h | converged with bounded-final-h confirmation |
| R(-5,0) s | `7.45730053677e-8` | `-9.81780791859e-5 - 6.53550324587e-5 i` | stable | strict monotone | converged |
| R(-4,0) s | `2.67523960967e-7` | `2.10223336125e-4 - 4.97304361281e-5 i` | stable | strict monotone | converged |
| R(-2,0) s | `1.47769085130e-6` | `4.94231617062e-4 - 2.05515769764e-4 i` | stable | strict monotone | converged |
| R(-1,0) s | `6.66930965425e-6` | `-1.03270771592e-3 + 7.67833921753e-4 i` | stable | strict monotone | converged |
| R(0,0) s | `7.53761220068e-4` | `-2.52523043536e-2 + 1.07741517021e-2 i` | stable | strict monotone | converged |

`R(-7,0)_s` 的 p 方向稳定；其 p4 h-series 的 power、amplitude-real
和 amplitude-magnitude 不是严格单调，但最终 h 误差被独立 h10
p5-to-p6 correction 加原绝对 floor 所界定，故没有伪造严格单调声明。

## 3. 失败通道独立 adjoint 与 DWR 语义

### 3.1 16 个独立目标

| goal family | goals | count | result |
|---|---|---:|---|
| failed power | R/T `(-2,0)`、`(-4,0)`、`(-5,0)` | 6 | 6/6 pass |
| failed complex amplitude | Re/Im of R `(-4,0)`、`(-5,0)`；T `(-2,0)`、`(-4,0)`、`(-5,0)` | 10 | 10/10 pass |
| total | independent real-valued Hermitian goals | 16 | 16/16 pass |

这些是实际离散 DtN/port functional 上的 `A^H z = g`，不是 plain
transpose，也没有用 power derivative 代替 complex amplitude derivative。
每个 complex channel 的 real 与 imaginary component 均使用独立 adjoint。

| measured quantity | value |
|---|---:|
| active matrix rows | 16,880 |
| MPI | 8 |
| max direct-adjoint relative error | `2.51443346242e-11` |
| max finite-difference relative error | `5.57543615395e-7` |
| max adjoint relative residual | `4.20650363445e-13` |
| adjoint elapsed | `10.3338125770 s` |
| diagnostic process-tree peak | `7.19028854370 GiB` |
| process-tree swap | `0 MiB` |

该 diagnostic 保留 forward factor、recovery cache 和全部 dual，因此其
7.190 GiB 不与正式候选 5.803 GiB 资源峰直接比较。首次 adjoint record
仅 2/16 通过，按合同保留为 `formal_not_pass`；verification v2 修正后才是
本节的 16/16 authority。

### 3.2 为什么 localization proxy 不是 DWR

| capability | status |
|---|---|
| actual Hermitian adjoint solves | `measured / pass` |
| exact augmented full-dual recovery | `measured / pass` |
| periodic transitive coefficient aggregation | `derived / available` |
| recovered-dual coefficient sensitivity | `derived proxy / available` |
| strict global-p6-trace enriched operator | `not_available` |
| lifted fixed-trace primal residual in enriched space | `not_available` |
| residual weighting | `false` |
| actual enriched DWR indicator | `false` |
| Lane B formal subset selection | `not_authorized` |

保存的 cell/face/edge 数值定义为：

```text
recovered_dual_coefficient_sensitivity_proxy
```

它是按 reference-v1 component band 归一化的 recovered-dual coefficient
绝对值聚合。它没有 enriched residual，不能写成 `DWR_R/T/channel(K)`，
也不能授权 trace subset。因而 Review V1 第 11 节中的独立 adjoint 已完成，
但“actual failed-channel DWR”准确状态是
`not_run_by_missing_enriched_residual_capability`。

## 4. 根因假设判别

| hypothesis | evidence | result | conclusion |
|---|---|---|---|
| z-direction mesh/topology resolution | global p6/h15 与 fixed-trace h15 共同失败；z h14/h13 连续恢复 | `measured positive` | 当前最强预算内恢复方向；支持 z-resolution 相关候选原因，不唯一识别 mesh、numerical phase 或 port/trace 耦合 |
| x resolution | fixed-trace `(7,2,10)` | 5/12 power，6/12 amplitude | `controlled negative` |
| y resolution mechanism control | global p5 `(6,3,10)` 与 `(6,2,10)` control | 均为 3/12 power，1/12 amplitude；normalized L2 几乎不变 | `controlled negative`；不是 same-space fixed-trace y 排除 |
| z resolution | fixed-trace `(6,2,11)` 与 `(6,2,12)` | 7/9 → 10/10 | 明确方向性正信号 |
| full trace degree | same-mesh global p6/h14 vs fixed-trace h14 | 9/12 + 12/12 vs 7/12 + 9/12 | measured positive marginal；不定位 missing-mode subset 或相对因果排序 |
| DtN surface quadrature | q31 | 6/12 + 7/12，与 seed 相同 | `controlled negative` |
| evanescent buffer | scaled buffer1，260 evanescent modes | 6/12 + 7/12；power/amplitude normalized L2 仅改善 0.202%/0.278% | 无 material recovery |
| tested port sign/phase/projection convention | artifact audit + independent manufactured Rayleigh authority | algebra、outgoing sign、two-plane phase、projection、power、evanescent coordinate 均 pass | 已测试约定未发现错误；不排除其他 DtN/port 离散效应 |
| one scalar recovery knob | response-matrix/SVD diagnostic | remaining power response rank≈2；complex rank=3 | 现有线性 response 诊断不支持预期单一标量 knob 闭合；未运行组合 PDE |

phase-dispersion 的 `delta_z_eff` 只是 complex-error-frame 诊断，不是几何或
port-plane correction。bottom reference-power-weighted fit 在 h15/h14/h13
依次为 `0.00853 / 0.00914 / 0.00980 nm`，没有形成收敛趋势；top fit
非单调，global-p6/h15 的 fit residual 又接近 raw phase。该记录只能提高
phase-bearing trace-orbit/DWR 审计优先级，不能证明 phase
under-resolution，也不能选择具体网格节点或 trace modes。

artifact-only port audit 能证明四份 authority 的约定一致，但单独不能排除
common-mode implementation error。随后独立 manufactured authority 将最大
reported error、source-free Maxwell residual、formula relative error 和
production-mode physics relative error 分别界定为
`2.22e-16 / 2.19e-16 / 5.36e-16 / 2.57e-16`；它显著加强 port
algebra 可信度，但仍不替代目标 PDE 的 full residual 与 12 通道 Gate。

未缩放 buffer1 的最小 boundary phase 为 `4.69874e-84`，远低于
`sqrt(machine epsilon)`，因此在 PDE 前安全停止；经过 boundary-referenced
scaling 后实际 PDE 可运行，但仍没有通道恢复。它证明未缩放 buffer1 的停止
是缩放安全问题，并给出已测试 scaled-buffer 扰动的负结果；external DtN
funnel 未运行，不能据此排除其他 DtN/port 离散效应。

## 5. 全部恢复候选与 controls

### 5.1 资源、时间和正式 Gate

下表中的 fixed-trace peak 是同时 process-tree peak；`global pair` peak
包含同一次 p4/p5 或 p5/p6 pair 生命周期，不能解释为单个场的独立峰。
NNZ、factor NNZ、row width、时间和 residual 均为 measured。

| lane / case | axis plan | DoF / rows | matrix NNZ / factor NNZ / fill | avg/max row | peak GiB | build/setup/solve s | true residual | power / amplitude | decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| fixed seed h15 | `(6,2,10)` | 74,890 / 16,880 | 9,195,812 / 27,916,600 / 3.036 | 544.776 / 965 | 5.803 | 61.613 / 6.557 / 0.0358 | `8.83e-12` | 6/12 / 7/12 | controlled negative |
| Lane A z h14 | `(6,2,11)` | 82,315 / 18,500 | 10,104,512 / 31,347,000 / 3.102 | 546.190 / 965 | 6.376 | 62.312 / 11.474 / 0.0315 | `4.45e-12` | 7/12 / 9/12 | positive signal；incomplete |
| Lane A z h13 | `(6,2,12)` | 89,740 / 20,120 | 11,013,212 / 36,273,200 / 3.294 | 547.376 / 965 | 6.411 | 59.855 / 13.342 / 0.0334 | `5.81e-12` | 10/12 / 10/12 | strongest in-cap negative |
| x-only control | `(7,2,10)` | 87,195 / 19,680 | 10,728,434 / 33,056,800 / 3.081 | 545.144 / 965 | 6.590 | 63.134 / 7.641 / 0.0334 | `1.44e-11` | 5/12 / 6/12 | controlled negative |
| y-only global-p5 control | `(6,3,10)` | 72,995 / 25,280 | 14,433,128 / 70,293,600 / 4.870 | 570.931 / 965 | 8.867 global pair | 22.848 / 31.685 / 0.0674 | `2.77e-11` | 3/12 / 1/12 | diagnostic negative |
| DtN q31 | `(6,2,10)` | 74,890 / 16,880 | 9,195,812 / 27,916,600 / 3.036 | 544.776 / 965 | 6.133 | 61.836 / 6.597 / 0.0323 | `1.08e-11` | 6/12 / 7/12 | controlled negative |
| scaled buffer1 | `(6,2,10)` | 74,890 / 17,140 | 9,472,792 / 31,655,400 / 3.342 | 552.672 / 965 | 6.558 | 61.534 / 14.655 / 0.0408 | `3.11e-12` | 6/12 / 7/12 | controlled negative |
| global p6/h14 discriminator | `(6,2,11)` | 92,850 / 27,080 | 21,110,096 / 67,325,792 / 3.189 | 779.546 / 1,398 | 12.587 global pair; 11.803 p6 solve-stage | 89.482 / 25.356 / 0.0627 | `1.47e-11` | 9/12 / 12/12 | over cap by 2,850 |
| h14 R5-slab bisect | `(6,2,12)` | 89,740 / 20,120 | 11,013,212 / 36,273,200 / 3.294 | 547.376 / 965 | 6.463 | 60.068 / 13.570 / 0.0348 | `5.59e-12` | 5/12 / 9/12 | controlled negative；预先指定 R5-slab lane closed |

失败通道映射为：

| case | failed power channels | failed complex-amplitude channels |
|---|---|---|
| fixed seed h15 | T/R `(-2,-4,-5)` | T `(-2,-4,-5)`；R `(-4,-5)` |
| z h14 | T `(-4,-5)`；R `(-2,-4,-5)` | T `(-4,-5)`；R `(-5)` |
| z h13 | T `(-4)`；R `(-4)` | R `(-4,-5)` |
| x-only | T `(-2,-4,-5,-7)`；R `(-2,-4,-7)` | T `(-2,-5)`；R `(-2,-4,-5,-7)` |
| q31 | 与 seed 相同 | 与 seed 相同 |
| scaled buffer1 | 与 seed 相同 | 与 seed 相同 |
| global p6/h14 | T `(-4,-5)`；R `(-4)` | none |
| h14 R5-slab bisect | T `(-2,-4,-5)`；R `(-2,-4,-5,-7)` | T `(-4,-5)`；R `(-5)` |

除 y-only mechanism control 外，上述正式 recovery PDE 均保持 scalar
`R00/R/T/Aclosure`、normalized vector、selected volume/interface field、
exact-sequence、geometry/tag/orientation/Floquet identity 和 full residual
Gate。`candidate_accuracy_pass=false` 来自 12 通道完整 Gate，不是把
scalar/field failure 隐去。

z h14 相对 seed 的 failed-channel normalized power/amplitude L2 分别改善
`73.072% / 62.359%`；z h13 分别改善 `88.124% / 30.819%`，并把
Gate count 推进到 10/10。x-only 使 Gate count 退化；y-only 与
scaled buffer1 的响应不足 5% material-improvement 判据。R5-slab 虽降低
部分旧失败误差，却新增 `R(-7,0)` power regression，故不继续 split-position
扫描。

### 5.2 最强 h13 候选的十二通道

| channel | candidate power | candidate complex amplitude | power Gate | amplitude Gate |
|---|---:|---:|---|---|
| T(-7,0) s | `2.36225288824e-6` | `9.81167544398e-4 - 8.84024041667e-5 i` | pass | pass |
| T(-5,0) s | `2.12204228069e-7` | `1.34725687090e-4 + 1.46551622295e-4 i` | pass | pass |
| T(-4,0) s | `4.35489199428e-7` | `-2.61125984121e-4 + 8.86378025759e-5 i` | **fail** | pass |
| T(-2,0) s | `2.95868518886e-6` | `-6.96291673953e-4 + 2.99225357519e-4 i` | pass | pass |
| T(-1,0) s | `2.17753807955e-5` | `2.09015756157e-3 - 1.02436264988e-3 i` | pass | pass |
| T(0,0) s | `6.02654698626e-1` | `6.31731380082e-1 + 4.72528917690e-1 i` | pass | pass |
| R(-7,0) s | `6.26378308638e-7` | `-5.05224210350e-4 - 2.59847102187e-5 i` | pass | pass |
| R(-5,0) s | `7.35017831938e-8` | `-1.00926387945e-4 - 5.93655036535e-5 i` | pass | **fail** |
| R(-4,0) s | `2.72339140129e-7` | `2.12784701368e-4 - 4.72186363878e-5 i` | **fail** | **fail** |
| R(-2,0) s | `1.47657836307e-6` | `4.93434424824e-4 - 2.06901901623e-4 i` | pass | pass |
| R(-1,0) s | `6.67510914774e-6` | `-1.03272204657e-3 + 7.68751847368e-4 i` | pass | pass |
| R(0,0) s | `7.56117570116e-4` | `-2.52711749561e-2 + 1.08390629878e-2 i` | pass | pass |

因此剩余失败标签为：

```text
power:    T(-4,0), R(-4,0)
amplitude: R(-5,0), R(-4,0)
union:    T(-4,0), R(-5,0), R(-4,0)
```

h13 scalar 值为：

| R00 | R total | T total | Aclosure |
|---:|---:|---:|---:|
| `0.000756117570116` | `0.000765246511550` | `0.602682451672149` | `0.396552301816302` |

## 6. Lane A、B、C 与并行方向的关闭依据

### 6.1 Lane A：方向性 structured-h

| step | signal | disposition |
|---|---|---|
| z h14 `(6,2,11)` | positive；7/12 + 9/12 | 继续到唯一必要的 h13 判别 |
| z h13 `(6,2,12)` | positive；10/12 + 10/12；DoF 89,740 | 达到预算边缘，仅余 260 DoF headroom |
| x-only `(7,2,10)` | negative；5/12 + 6/12 | lane control closed |
| y-only global-p5 `(6,3,10)` | normalized response essentially zero | 指定 mechanism control 关闭；不是 same-space y 排除 |
| h14 R5-slab bisect | 5/12 + 9/12，新增 R(-7) power regression | 预先指定 R5-slab split lane 关闭 |

继续增加整层 z 分段会越过 90k DoF；同 DoF 的预先指定 R5 slab
alternative 已给出负信号。故 Lane A 以“强正恢复趋势但 incomplete formal
Gate”收口，而不是无边界 h 扫描。其他 node distributions 未被证明无效，
本批次也未运行。

### 6.2 Lane B：selective p6 trace

same-mesh global p6/h14 将 fixed h14 的 `7/12 + 9/12` 提升到
`9/12 + 12/12`，给出 trace degree 的测得物理正信号。但完整 trace
increment 为：

| mesh | fixed DoF | full p6 trace increment | headroom | full-trace result |
|---|---:|---:|---:|---|
| h14 `(6,2,11)` | 82,315 | 10,535 | 7,685 | 92,850；超上限 2,850 |
| h13 `(6,2,12)` | 89,740 | 11,468 | 260 | 101,208；超上限 11,208 |

reference-cell complement 已严格分解出 132 个 missing trace modes：

```text
12 edges × 1 mode
+
6 faces × 20 modes
=
132 modes/cell
```

reference-cell direct sum、orientation 和 tangential-L2 Riesz 均通过，但
以下物理能力仍缺失：

- physical-cell Piola/Riesz 与 cross-entity Gram；
- missing-mode orientation/Floquet phase pullback 和 closed periodic orbits；
- actual global missing-trace residual 与 complement Schur inverse；
- true active global numbering 和 orbit cost；
- residual-weighted enriched DWR；
- selected subset exact-sequence closure；
- physically reduced candidate rows/assembly。

因此 [`physical_trace_lane_capability_gate.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_trace_lane_capability_gate.json)
记录：

```text
status = capability_stop_not_run
candidate_count = 0
pde_run_count = 0
subset_selected = false
lane_b_selection_authorized = false
```

这不是“保留完整 p6 矩阵后置零”的替代实现。逆向用 p6 trace 换低阶
interior 也未绕过 Gate：`p6-trace/p5-interior` 缺 101 个 gradient
modes，`p6-trace/p4-interior` 缺 149 个，均在 PDE 前 exact-sequence
fail-closed。

### 6.3 Lane C：最小组合

channel response matrix 将 z h13 识别为最佳单 lane，但没有任何 pair
相对该点达到 5% joint improvement 且保持 Gate count 不退化：

- z h13 + x：不支持；
- z h13 + scaled buffer1：预测 joint improvement 仅 `0.0243%`；
- z h13 + y：不同 mechanism control，不可直接组合；
- z h13 + z h14：替代 topology，不是可叠加 lane；
- selective trace：当前 capability-stop，无法形成合法 candidate。

因此 Lane C 为 `not_run_by_lane_gate`。没有把线性 response projection
冒充 PDE，也没有盲扫组合。

### 6.4 其他并行方向

| direction | evidence semantics | conclusion |
|---|---|---|
| p7/h10 | `predicted + capability_stop` | raw Basix p7 存在，但 qualified trace/Floquet/condensation 只到 p6；projected 273,581 DoF、70,640 rows、约 78.09M matrix NNZ，PDE 未运行 |
| channel-aware trace basis | `structural groundwork` | 132-mode complement/Riesz pass；physical/orbit/DWR ranking 未授权 |
| port/DtN authority | `measured diagnostic + manufactured algebra` | 已测试 convention/q31/scaled-buffer 扰动没有 material recovery；未覆盖 external funnel |
| condensed iterative | `capability_stop_not_run` | 当前 PETSc 无 HYPRE；无 dedicated solver profile、residual history 与 factor-free inventory contract |
| inversion-aware selection | `not_run` | 缺真实反演参数、噪声和测量可用性；不得删除 12 通道 |

condensed iterative capability audit 绑定 fixed h15 direct baseline。其
MUMPS factor-storage planning proxy 为 `0.624 GiB`，约为 measured
5.803 GiB peak 的 10.76%；`5.179 GiB` 的“peak 减 storage proxy”只是
算术 envelope，不是 measured 或 predicted iterative peak。正式 MPI8
GMRES screen 为 `not_run`，故没有迭代收敛或内存声明。

## 7. Hybrid、M/DtN funnel 与 0.7 nm / 2 TiB

```text
selected Full3D candidate = null
Full3D-Hybrid same-degree closure = not_run_by_selected_candidate_gate
M80/M120/M160/M240 funnel = not_run
external DtN order/evanescent-buffer funnel = not_run
12-channel Hybrid closure = not_run
resource model v3 = not_run_by_hybrid_gate
0.7 nm PDE = not_run
predicted simultaneous peak = null
2 TiB production feasibility = unknown
```

scaled buffer1 是 Full3D root-cause diagnostic，不是 Review V1 第 15 节的
post-selection external DtN funnel。没有完整 Full3D 候选时，后续
Hybrid 和 resource-model 数值不具备布局身份，因此未把旧 component sum、
planning factor 或 DoF projection 写成 simultaneous peak。

## 8. Controlled negatives、未运行项与硬 blocker

| item | final classification |
|---|---|
| initial channel-adjoint implementation | `formal_not_pass`；保留，未删除 |
| x-only、y-only、q31、scaled buffer1 | `controlled_negative` |
| h14/h13 z | positive recovery signal，但 formal candidate 仍 `controlled_negative` |
| h14 R5 slab bisect | `controlled_negative`；不再扫描 split position |
| global p6/h14 | physics discriminator；`not_candidate_over_dof_cap` |
| unscaled buffer1 | `controlled_stop_before_PDE` |
| p7/h10 | `controlled_stop_before_PDE` |
| inverse trace/interior exchange | `controlled_negative_preflight` |
| physical selective trace | `capability_stop_not_run` |
| condensed iterative | `capability_stop_not_run` |
| Lane C / Hybrid / resource model v3 | `not_run_by_gate` |

当前没有需要用户输入密码、修复 ABI、恢复 source identity 或处理资源安全
风险的硬 blocker。未完成项是明确的 numerical/capability gap，不是用户
操作 blocker。普通默认未修改，历史 failed/controlled-negative evidence
全部保留，也未触碰 irregular geometry 或 `master`。

## 9. 关键 evidence 索引

| evidence | record SHA256 | source SHA / identity |
|---|---|---|
| [`significant_channel_reference_v1.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/significant_channel_reference_v1.json) | `83b7bcfeb510b849aea391d86f306072ead0232781598ea1232617e2535293e3` | manifest `c8538133617ffbeffb1de2f18f8a7134082018f9f85d6a50ea72e0e83ff718b2` |
| [`fixed_p5trace_p6interior_h15_channel_adjoints_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_channel_adjoints_mpi8.json) | `a983acf954c1270d080b5c47430ddc3c348eb0041ad4c705c5486f07a72cfba3` | `ab28bf878b8446e2699fa3cbff80e85f8013cad6` |
| [`fixed_p5trace_p6interior_h15_channel_adjoints_verification_v2_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_channel_adjoints_verification_v2_mpi8.json) | `56023fcbf5a85d8d5d2db062283cae8b66771c1543d025731a0c9eefa4a8d0e5` | `572c4ff3eb2bf360a72a593a105f5cd628c985c8` |
| [`fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_tensor_dedup_preallocation_mpi8.json) | `1ffde81be08c24232e62c1d2dfbf1b7ad2dcb3623444ea40af68b5c6585758e3` | `7f61d554b0441d7b224c096aba402d3b3ac2baa6` |
| [`fixed_p5trace_p6interior_h14_directional_z_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_directional_z_mpi8.json) | `e93f50155b3c8517292794cb9735730ebf738410aecafe00f43f7959c150a127` | `d958b2bfc5eaf9920f3220a519d20b11e5da3248` |
| [`fixed_p5trace_p6interior_h13_directional_z_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h13_directional_z_mpi8.json) | `81ba43d91c4c9a35121676ae40368d56116f3a381e4559d630fb547a94dc4a5c` | `df4046f8ba9f319a2501c6a0376a7c81063b5905` |
| [`fixed_p5trace_p6interior_h15_directional_x_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_directional_x_mpi8.json) | `0e469bd9f952652f102c33d8d0d7c14827a0a492bb2611971cafdc66a3b7bd2c` | `1550c204d1e6ec7518a830c027f22b529360866a` |
| [`global_hexa_p4_p5_h15_directional_y_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p4_p5_h15_directional_y_mpi8.json) | `8070ff6a7df90490421724fe1f399a60cbe168b55d153f7f9b0a2cf5e8d1b192` | `5835744ae32a0dc17ebc8c5067333cff9c33e5ee` |
| [`y_only_global_p5_directional_control_comparison_v1.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/y_only_global_p5_directional_control_comparison_v1.json) | `6263db07dc6bc3d9b4a2d2be8af529a0f471f0b0e123a9c77044fef129cc9236` | `589fd5fa876f9048b19f73a567c46ab4b427bca1` |
| [`fixed_p5trace_p6interior_h15_dtn_q31_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_dtn_q31_mpi8.json) | `b4dc00a5ae0cd1076b14725789c66c71d9f66869b7f25a3b152992785fbf6a04` | `ae86e7ad3722638245a425829427c0139c15ef77` |
| [`fixed_trace_h15_evanescent_buffer1_preflight_controlled_stop.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_trace_h15_evanescent_buffer1_preflight_controlled_stop.json) | `1dbc1c4388c4c67a9b9d84a9e1f9c0ad1636cfd582e719b51f73d00dbb61e000` | `7139a6e2ee0bcec4459e7591864235bbbc7d7377` |
| [`fixed_p5trace_p6interior_h15_dtn_evanescent_buffer1_scaled_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h15_dtn_evanescent_buffer1_scaled_mpi8.json) | `2f76568d7013662602293e18ce75e33f6ecd625d723bc1cf745964a1a4541206` | `7d90a409dc7274dad6863df5093ed219d2ad2a22` |
| [`dtn_port_phase_authority_v1.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/dtn_port_phase_authority_v1.json) | `863b8469796cdd2bbe367819b65e9bd8388d247c214cb941694b04c330b41401` | record commit `7139a6e2ee0bcec4459e7591864235bbbc7d7377` |
| [`manufactured_rayleigh_port_authority_v1.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/manufactured_rayleigh_port_authority_v1.json) | `080677adc33226ea13dfad9610c62b3ae26896667a0ac6fbeee969217060652b` | `c8874ad4d6d73679f2bfd4a828186b41386f1004` |
| [`channel_response_matrix_directionality_v1.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/channel_response_matrix_directionality_v1.json) | `1459b89f8135ff028c8fff0b1e8552295c83105cd420ee3a382c6baf6d4618de` | `b1f38708614bb54190f933e657723a70d047682c` |
| [`channel_phase_dispersion_diagnostic_v1.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/channel_phase_dispersion_diagnostic_v1.json) | `21fa66f1babc5dc59c5bb919f56a09814bdbf3bd146d244565476bfc8218167f` | `206a4a93d3098e04c97ed3b53d726f42d4be2e95` |
| [`global_hexa_p5_p6_h14_assembly_time_condensed_independent_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_hexa_p5_p6_h14_assembly_time_condensed_independent_mpi8.json) | `61318008f0168b5b27c2b436e18354a57f634b1826a1f051b42d63af8844d35b` | `b37154fa078962a94db47779e571dc65fa653893` |
| [`global_p6_h14_trace_discriminator.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/global_p6_h14_trace_discriminator.json) | `a16bb533222a73cbe5dede8b3abe93d2e047ef168a6ebc74e85790433f767cad` | `03496d4d7b419e2826332cf5bf0573fde4aab409` |
| [`missing_p6_trace_complement_preflight_v2.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/missing_p6_trace_complement_preflight_v2.json) | `899b320ed6659f745cb1ed8532cb6752cdfca338c703f1608cd4233473370a32` | `5c2045305049008082021326a74311a64c190d4c` |
| [`inverse_trace_interior_budget_exchange_preflight.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/inverse_trace_interior_budget_exchange_preflight.json) | `d010d69d26429993c1f07725a4b63653cf6d79d1155ea4eef76d0077c3b189f9` | `a6e572f991674540a8b760d4ebe23fe663594c70` |
| [`p7_h10_capability_resource_gate.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/p7_h10_capability_resource_gate.json) | `2671f93a5dc4b087df4c3911f022796a4312082bd98dcc954c725ac9607ffbb6` | `fd8cb45ecf4ca9b2e424315e757606a7a0d8e312` |
| [`fixed_p5trace_p6interior_h14_r5_slab_bisect_mpi8.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/fixed_p5trace_p6interior_h14_r5_slab_bisect_mpi8.json) | `eb9f1d8e30e6d0aab0c3fe377939c4335485634044fa3be4b8956ac748b411e3` | `6ee517bf96a9022ae129070b822e281da030f617` |
| [`physical_trace_lane_capability_gate.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/physical_trace_lane_capability_gate.json) | `4f26763ffc182925b0f92a20674f9572235205237d0e1a6677b92cc992d9d2bc` | `4a9bf317562c5713f1da0cf5597fcaecedce38e0` |
| [`condensed_trace_iterative_capability_gate.json`](../../benchmarks/cases/095_high_order_local_hp_resource_envelope/records/condensed_trace_iterative_capability_gate.json) | `3597379e4a62dfefd3ac53ded8d2a12d91422cc8f9ebfac4af2d657a43cd7048` | `5b652793047b58bdd25aaa96385c2a739c69fce9` |

## 10. Final-HEAD 测试与交付占位

本节不复用旧 HEAD 的计数，也不虚构尚未由主智能体在最终文档/ledger
收口后执行的结果。以下项目必须在最终改动完成后由主智能体填写。

| final check | command/scope | result | status |
|---|---|---|---|
| focused Task035b tests | final changed components | `<TO_BE_FILLED>` | `pending_final_head` |
| MPI regression | required MPI2/MPI8 focused set | `<TO_BE_FILLED>` | `pending_final_head` |
| Task034/035/035b regression | task-focused suite | `<TO_BE_FILLED>` | `pending_final_head` |
| full repository pytest | qualified WSL activation | `<TO_BE_FILLED>` | `pending_final_head` |
| Ruff | final scoped/full result with inherited findings separated | `<TO_BE_FILLED>` | `pending_final_head` |
| compileall | final touched Python scope | `<TO_BE_FILLED>` | `pending_final_head` |
| tracked JSON parse/hash audit | final record and candidate ledger count | `<TO_BE_FILLED>` | `pending_final_head` |
| Markdown/link/doc-contract checks | final docs | `<TO_BE_FILLED>` | `pending_final_head` |
| `git diff --check` | final worktree | `<TO_BE_FILLED>` | `pending_final_head` |
| final branch / HEAD | exact full SHA | `<TO_BE_FILLED>` | `pending_final_head` |
| final `git status --short --untracked-files=all` | must be reported exactly | `<TO_BE_FILLED>` | `pending_final_head` |
| remote push identity | branch and remote full SHA | `<TO_BE_FILLED>` | `pending_final_head` |

最终提交和 push 是交付步骤，不是新的研究 Gate；未经后续 Review 和用户
明确授权，不得合并 `master`。
