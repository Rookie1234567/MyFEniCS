# Task035b Review V4：任务闭合与 Task035c Hybrid 精度/内存专项授权

## 1. 审阅结论

```text
review_status = TASK035B_CLOSED_WITH_CONTROLLED_NEGATIVES
reviewed_branch = codex/20260726-task35b-high-order-local-hp-resource-envelope
reviewed_response = response_v5.md
reviewed_numerical_source = 148729c28c3f9aefec8e5646cc644c5c4e2332da
master_baseline = 1fb144d3ca50208c22b5f0733e140bfac8d9c47c
Task035b_completion = complete_by_scope_and_stop_rules
Task035b_final_scientific_status = PARTIAL_WITH_CONTROLLED_NEGATIVES
Task035b_second_master_merge = not_authorized
Task035c = authorized
Task035c_branch = codex/20260726-task35c-hybrid-channel-memory-closure
Task035c_scope = Hybrid channel accuracy root cause + static-Hybrid memory/time closure
ordinary_default_changed = false
```

Task035b 可以闭合。

这里的“闭合”不表示 Task035b 找到了满足全部目标的最终自适应模型，而是表示：

1. 原任务规定的高阶 p/h、静态凝聚、资源包络、setup/cache、direct rank study、迭代筛选、Hybrid 接入和停止规则均已执行到可审查终点；
2. 正结果、负结果、未运行项和能力边界均有正式 evidence；
3. H1-A 已经把剩余问题明确分解为两个新的、独立的工程问题；
4. 继续在 Task035b 中叠加 p2/h3、高阶或 h13 自适应，只会把尚未解释的 Hybrid 误差和资源瓶颈带入更重模型，不能增加结论可信度。

因此 Task035b 的最终身份为：

```text
高阶与静态凝聚基础设施：成功
预算内 same-error h/p 最终候选：未获得
static Hybrid 代数实现：成功
Full3D–Hybrid 严格逐通道闭合：失败，原因未定位
static Hybrid 内存/时间收益：未获得
任务执行：按 Gate 正确停止并闭合
```

剩余两项必须拆分为 Task035c：

- 为什么 Full3D 和 Hybrid 在总 R/T/A、残差和场范数接近时，弱衍射级功率与复振幅仍有显著误差；
- 为什么 Hybrid 减少了 rows 和 matrix NNZ，峰值内存却没有下降，时间反而接近翻倍，以及怎样真正把内存降下来。

---

## 2. Task035b 为什么已经达到可闭合状态

### 2.1 已完成并进入 master 的主线能力

Task035/035b 已完成文件级选择性合并，master 为：

```text
1fb144d3ca50208c22b5f0733e140bfac8d9c47c
```

已进入 master 的主要能力包括：

- 原始完整矩阵 direct 路径，ordinary default 不变；
- 统一用户端口 `standard_full / assembly_time_static_condensed`；
- p5/p6 Nédélec、高阶 orientation、双 Floquet 与 MPI identity；
- Full3D assembly-time cell-interior static condensation；
- Floquet slave 在全局插入前消除；
- 完整场恢复、full explicit residual 和正式 R/T/A/衍射级；
- tensor/class reuse、exact preallocation、bulk insertion、cold/warm cache；
- periodic tetra、DWR 和 p5/p6 research-grade 基础设施；
- 模型总账、Case094/095 精简权威 evidence 和治理规则。

该部分已通过选择性整合测试，旧 stacked branch 没有整体 merge。

### 2.2 Task035b 的主要科学负结果已经稳定

预算内最强 Full3D 候选仍为：

```text
fixed p5 trace + p6 cell interior
directional-z h13
Full3D-equivalent DoF = 89,740
active rows = 20,120
significant powers = 10/12
significant complex amplitudes = 10/12
```

未通过对象为：

```text
T(-4,0) power
R(-4,0) power
r(-4,0)
r(-5,0)
```

后续两个固定 DoF 的 z-node 判别点继续退化，说明当前路线没有遗漏一个显而易见的低成本修复点。selective p6 trace 尚无正式 PDE；regionwise/inverse p 空间中又存在 exact-sequence 失败。Task035b 因此没有满足原来的 12/12 + 12/12 same-error 目标，但已按合同形成可信的受控负结论。

### 2.3 H0 静态凝聚 Hybrid 已完成正确性证明

H0 已经证明：

- Full3D standard 与 Full3D static：12/12 功率、12/12 复振幅等价；
- Hybrid standard 与 Hybrid static：M120 和 M160 均为 12/12 + 12/12 等价；
- static Hybrid M120→M160：12/12 + 12/12 收敛；
- full operator residual、被消去 interior 方程残差和流式完整场恢复均通过。

这说明静态凝聚接入 Hybrid 的代数实现本身是正确的。它没有错误消去 external DtN、modal amplitudes 或 Hybrid 接口切向 trace。

### 2.4 H1-A 已暴露新的跨方法问题

同一 p2/h5 离散下：

```text
static Full3D vs static Hybrid M160
Task033 relative gate: 3/12 powers + 2/12 amplitudes
strict absolute gate: 2/12 powers + 2/12 amplitudes
```

M120 增至 M160 后结果几乎不变，因此不能继续把误差简单归因于 M 截断不足。

与此同时：

- 总 R/T/A 很接近；
- full residual 很小；
- interface E/H 和 selected-plane field error 达到原有 Gate；
- 但多个 `10^-6`–`10^-8` 量级弱衍射级存在显著功率和相位误差。

这已经不再是 Task035b 原始的“高阶 local-hp 资源包络”问题，而是 Hybrid 模态表示、接口传递和逐通道后处理的专项问题。

### 2.5 H1-A 的资源结果也已形成清楚的新问题

p2/h5 Hybrid M160：

| metric | standard | static | change |
|---|---:|---:|---:|
| total rows | 14,052 | 10,000 | -28.84% |
| local matrix NNZ pair | 1,454,248 | 976,400 | -32.86% |
| factor NNZ pair | 6,390,216 | 5,986,184 | -6.32% |
| factor fill | 4.394 | 6.131 | +39.52% |
| process-tree peak | 3.285 GiB | 3.308 GiB | +0.71% |
| total time | 96.28 s | 186.36 s | +93.56% |
| internal modal coupling | 11.72 s | 110.62 s | +843.7% |

因此“减少自由度”没有自动转化成“降低峰值内存”。当前实测瓶颈不是 MUMPS，而是 static left/right modal correction 以及与其重叠的局部 Schur、recovery、QEP/mode 和 coupling 数据生命周期。

这同样需要独立的内存对象账本和算法重构，适合进入 Task035c，而不应继续作为 Task035b 的附带优化。

---

# 3. Task035c 正式授权

## 3.1 任务名称与分支

新任务名称：

```text
Task035c：Hybrid significant-channel accuracy and static-condensation memory closure
```

执行分支：

```text
codex/20260726-task35c-hybrid-channel-memory-closure
```

Task035c 直接依赖尚未进入 master 的 H0 static-Hybrid 实现，因此该分支应从包含本 Review 的 Task035b 最终提交继续，而不是从 master 重新复制实现。Task035b 分支在本 Review 后冻结，不再继续增加无关模型。

Task035c 必须新建独立目录：

```text
docs/task035c_hybrid_channel_memory_closure/
```

并维护：

- `README.md`；
- `task.md`；
- `outcomes/summary.md`；
- `outcomes/test_summary.md`；
- 逐阶段诊断与 compact records；
- `response_vN.md`；
- `docs/development_model_registry.md` 的 Task035c 条目。

## 3.2 Task035c 只解决两个问题

### 问题 A：Hybrid 逐衍射级精度

回答并修复：

> 为什么 Full3D 与 Hybrid 的总 R/T/A、残差和场范数可以接近，但 12 个显著通道中的多数弱功率与复振幅仍不一致？

必须区分并量化：

- modal cross-section 离散误差；
- QEP 特征值/特征向量的物理误差；
- biorthogonal/flux normalization；
- matching-trace projection；
- 100 nm 中间段传播相位；
- forward/backward mode pairing；
- interface E/H 传递；
- Rayleigh/Fourier 通道后处理和参考平面；
- Full3D 与 Hybrid 是否真正使用同一物理、材料、相位和 normalization。

### 问题 B：static Hybrid 内存和时间

回答并修复：

> 为什么 rows 和 assembled NNZ 已减少约 30%，factor 只减少约 6%，峰值不降、fill 增长且 internal modal coupling 变慢约 9.4 倍？

目标不是继续报告 DoF 压缩，而是使 static Hybrid 在同物理精度下真正降低 simultaneous peak memory，并把额外耦合时间压到合理范围。

Task035c 不做：

- h13 Hybrid 自适应；
- irregular geometry；
- tetra static condensation；
- mixed mesh；
- production selective trace；
- 新的 condensed iterative profile；
- 0.7 nm 资源外推。

上述内容只有在 Task035c 同时完成精度和内存闭合后才可恢复。

---

# 4. 必须计算的两个模型层级

用户要求不能只用 p2/h5。Task035c 必须同时包含一个高阶、已有等精度证据的模型。

## 4.1 Mandatory Model A：p2/h5 诊断模型

用途：

- 低成本复现当前 Full3D–Hybrid 通道误差；
- 支持逐组件替换、oracle trace、传播相位和内存对象审计；
- 不是最终物理收敛 authority。

必须保留四路：

```text
Full3D standard
Full3D static
Hybrid standard M120/M160
Hybrid static M120/M160
```

## 4.2 Mandatory Model B：p3/h7.5 高阶等精度模型

Task033 已将 `p3/h7.5` 识别为 fixed-p equal-accuracy clear success with qualifications。Task035c 将其作为强制高阶 anchor，而不是把 p2/h5 的粗 modal discretization 结果外推到高阶。

必须至少计算：

```text
Full3D standard p3/h7.5
Full3D static p3/h7.5
Hybrid standard p3/h7.5 M120/M160
Hybrid static p3/h7.5 M120/M160
```

必须用本任务新的 12 通道功率和12通道复振幅严格 Gate 重新资格化；不得仅引用 Task033 的总 R/T/A 和场 Gate。

`p3/h7.5` 是当前“高阶等精度工程 anchor”，不是 continuum truth。最终仍需与 p6/h10/reference v1 的趋势对照。

## 4.3 条件 Model C：p6/h10 或等价 global-p reference

只有在 p3/h7.5 给出明确根因信号且资源预估安全时，才允许运行一个 p6/global-p Hybrid 诊断点。该点用于确认修复能否迁移到 best available high-p reference，不作为 Task035c 的启动前置条件。

---

# 5. Hybrid 精度根因诊断顺序

必须按以下顺序执行，不得从参数盲扫开始。

## 5.1 P0：冻结完全相同的比较合同

对 Full3D 和 Hybrid 逐项核对并 hash-bound：

- 几何和材料分区；
- 波长、入射角、偏振和 Floquet 相位；
- external DtN order set；
- incident/reference field；
- port normalization；
- diffraction order indexing；
- reference plane 和传播相位；
- R/T power normalization；
- complex amplitude convention；
- MPI partition-independent identity。

发现任何不一致时先修复合同，不能继续解释为“Hybrid 近似误差”。

## 5.2 P1：统一逐通道后处理

必须证明：

1. Full3D 场和 Hybrid 恢复场在同一物理平面上调用同一个 Rayleigh/Fourier 后处理；
2. 使用相同 basis、normalization、phase origin 和 power flux；
3. 从同一个场重复计算的12通道结果逐位一致；
4. 改变输出参考平面只产生可预测的传播相位，不改变功率。

先排除后处理和参考相位差，再研究 QEP/接口误差。

## 5.3 P2：QEP 与 modal basis 的物理误差

M120→M160 收敛只说明“在当前离散 modal basis 内增加模态已稳定”，不说明该 basis 本身准确。

必须报告：

- QEP polynomial residual；
- beta 的物理误差或跨网格收敛；
- right/left eigenvector biorthogonality；
- flux normalization；
- forward/backward pairing；
- mode tracking；
- interface trace completeness；
- p2/h5 与 p3/h7.5 的 beta、mode shape 和传播相位差。

特别检查：

```text
phase error ≈ Δbeta × middle_length
```

小 beta 误差经过约100 nm传播后，可能对总场范数影响很小，却显著改变弱衍射级的相消与相长。

## 5.4 P3：interface projection 与 oracle 实验

至少完成三类隔离实验：

### Oracle A：Full3D interface trace → modal projection/reconstruction

从 Full3D 提取 Hybrid 上下接口的切向 E/H，投影到当前 modal basis，再重构并报告：

- E/H projection residual；
- 每个保留模态系数；
- 12通道灵敏度；
- p2/h5 与 p3/h7.5 的变化。

### Oracle B：Full3D interface trace → modal propagation → 同一后处理

直接使用 Full3D interface 数据驱动中间 modal propagation。如果此时逐通道仍失败，问题在 modal basis/propagation；如果通过，问题在 Hybrid local-FE ↔ modal coupling。

### Oracle C：Hybrid interface trace → Full3D-compatible reconstruction

把 Hybrid 解出的 interface trace 放回同一重构/后处理链，区分：

- 接口解本身错误；
- 中间传播错误；
- 输出通道投影错误。

## 5.5 P4：channel-sensitive diagnosis

对失败最严重的通道：

```text
T(-5,0)
T(-4,0)
T(-2,0)
T(-1,0)
R(-7,0)
R(-5,0)
R(-4,0)
R(-2,0)
R(-1,0)
```

使用已有 channel adjoint/response-matrix 基础设施，定位误差对：

- 哪些 interface modes；
- 哪些 beta/phase；
- 哪些 trace components；
- 哪个 local side；
- 哪个后处理投影；

最敏感。不得只继续提高 M。

---

# 6. static Hybrid 内存与时间根因

## 6.1 M0：建立同时峰值对象账本

对 p2/h5 和 p3/h7.5 的 standard/static Hybrid，分阶段记录：

- mesh/function-space；
- raw local tensors；
- `Aii` LU；
- local Schur/recovery arrays；
- external DtN vectors；
- internal modal right/left vectors；
- interface projection；
- left/right modal correction；
- augmented或modal-Schur matrix；
- MUMPS factor；
- full-field recovery；
- postprocessing。

内存至少同时报告：

```text
process-tree RSS
rank PSS sum
rank USS sum
cgroup current/peak
swap
Python/NumPy retained native bytes
PETSc matrix/factor inventory
```

必须指出峰值时刻哪些对象同时存活，不能用各阶段独立峰值相加。

## 6.2 M1：审计 cell-interior 与接口耦合支持

H(curl) cell-interior basis 的切向 trace 理论上应在 cell boundary 上为零。Task035c 必须显式审计：

```text
B_i = interior-to-modal coupling
C_i = modal-to-interior coupling
```

对真正的纯界面边界耦合，若理论上应为零，则必须证明数值上接近零，并删除无意义的 left/right Schur correction。

若当前 Hybrid formulation 确实通过 volume lifting 使 `B_i/C_i` 非零，则必须：

- 明确写出弱式来源；
- 证明该 coupling 必要；
- 与纯 trace formulation 做代数等价测试；
- 说明为什么标准 Hybrid 不需要同样成本。

这是同时解释“通道误差”和“110.6 s modal correction”的优先检查项。

## 6.3 M2：优化 modal correction

只有确认数学上必要的 correction 才可保留。实现必须优先考虑：

- 按 tensor/orientation class 批量计算；
- 一次 LU、多 RHS BLAS/LAPACK solve；
- M 分块 streaming；
- 低秩 factorized coupling，不形成长期 `N_FE × M` dense payload；
- 不逐 cell、逐 mode 进入 Python 小循环；
- standard/static 共用 modal basis 与projection cache；
- augmented 与 modal-Schur 两条路径避免重复构造同一 coupling；
- coupling 完成后尽早释放 raw tensor、临时 RHS、QEP workspace 和不再需要的 local factors；
- postprocess 需要恢复时采用 bounded streaming/recompute，而不是让 recovery cache 跨越 MUMPS 峰值。

## 6.4 M3：rank 与生命周期

对高阶 authority 至少比较 MPI1/2/4/8 中合理的两个或三个点。Hybrid 矩阵较小，过多 MPI rank 的进程复制可能抵消凝聚收益；不得默认 MPI8 是最低内存配置。

---

# 7. Task035c 成功 Gate

## 7.1 精度 Gate

### p2/h5 诊断点

Task035c 必须做到以下之一：

1. 修复后 Full3D ↔ Hybrid 达到12/12 powers + 12/12 amplitudes；或
2. 证明 p2/h5 的 modal cross-section 本身未解析，给出随 modal mesh/p 增加的单调收敛证据，并在 independently converged modal basis 上达到12/12 + 12/12。

不能以“p2/h5 太粗”一句话结束，也不能继续只看总 R/T/A。

### p3/h7.5 高阶 authority

必须在同一 p/h/M 下通过：

- standard Full3D ↔ static Full3D：12/12 + 12/12；
- standard Hybrid ↔ static Hybrid：12/12 + 12/12；
- corrected Full3D ↔ corrected Hybrid：12/12 + 12/12；
- Rtotal/Ttotal/Aclosure/Avolume；
- full residual；
- interface E/H；
- selected field planes；
- M120→M160，必要时有证据才进入 M240。

不得放宽 Task035b reference-v1 的逐通道 tolerance 来获得通过。

## 7.2 内存 Gate

p3/h7.5 是主要资源 authority。相同物理、p/h/M、MPI和输出合同下：

```text
mandatory static-Hybrid peak reduction >= 15%
preferred static-Hybrid peak reduction >= 25%
```

同时：

- static total rows 与 NNZ 必须保持下降；
- factor fill 不得无解释恶化；
- factor NNZ 应有可测下降；
- internal modal coupling 不得再比 standard 慢 9 倍；
- mandatory coupling time `<=1.25× standard`，优选快于 standard；
- mandatory total time `<=1.35× standard`；
- 不允许长期保留 full `N_FE × M` dense payload；
- 0 swap，或按资源 Gate 明确受控停止。

若 p2/h5 因固定开销导致峰值收益不明显，但 p3/h7.5 达到上述 Gate，可判定高阶 Hybrid 内存成功；必须解释规模交叉点，不能隐藏低阶负结果。

## 7.3 Task035c 最终分类

只有精度 Gate 和内存 Gate 同时通过，才允许：

```text
Task035c = HYBRID_CHANNEL_AND_MEMORY_CLOSURE_SUCCESS
```

若只定位根因但未修复，则为：

```text
PARTIAL_ROOT_CAUSE_IDENTIFIED
```

若修复精度但内存未下降，则为：

```text
PHYSICS_SUCCESS_RESOURCE_NEGATIVE
```

若只降内存但逐通道失败，则仍为失败，不得进入 h13 adaptive Hybrid。

---

# 8. Task035c 完成后的后续关系

只有 Task035c 达到完整成功后，才重新开放：

- `fixed p5-trace + p6-interior directional-z h13` Hybrid；
- Hybrid h/p 自适应；
- 0.7 nm / 2 TiB resource model v3；
- static Hybrid 进入 master 的第二次选择性合并审查。

Task035c 不应顺便开始 h13 adaptive。先把 Hybrid 作为一个可信且真正省内存的底层方法闭合，再进入新的自适应任务。

---

## 9. 合并与分支决定

当前 `codex/20260726-task35b-high-order-local-hp-resource-envelope` 的 H0/H1-A 提交不在本 Review 中批准第二次 merge master。

原因：

- H0 代数实现正确，但 Full3D–Hybrid 逐通道精度未闭合；
- static Hybrid 当前没有内存或时间收益；
- 这些代码是 Task035c 的必要起点，但尚不是可向普通用户宣传的完成能力。

处置：

1. Task035b 原分支提交本 Review 后冻结；
2. Task035c 分支从包含本 Review 的精确提交继续；
3. Task035c 完成后统一审查 Hybrid 修复、内存优化和是否选择性合并；
4. ordinary default 始终为 `standard_full`；
5. 已进入 master 的 Full3D static backend 不受影响。

---

## 10. 最终决定

```text
Task035b = CLOSED_WITH_CONTROLLED_NEGATIVES
Task035b achieved reusable high-order/static-condensation infrastructure = yes
Task035b achieved final same-error hp candidate = no
Task035b achieved physically qualified memory-saving static Hybrid = no
remaining questions are sufficiently isolated for successor = yes
Task035c = AUTHORIZED
Task035c mandatory models = p2/h5 + p3/h7.5
Task035c primary completion gate = 12-channel physics + measured memory reduction
```

Codex 在读取本 Review 后，应在 Task035c 分支建立独立任务目录和任务书，然后连续执行。任何重型 PDE 前必须先完成物理身份、后处理身份、QEP/trace 诊断与内存对象账本；不得直接以更大的 M、p2/h3、p6 或 h13 参数扫描代替根因分析。
