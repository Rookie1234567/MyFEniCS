# Task036 Review Report V6：从 exact FE trace-chain 回到可压缩 Hybrid

## 1. 审阅身份与决定

```text
review                         = Task036 Review V6
branch                         = codex/20260730-task36-forward-solver-bugfix-hardening
reviewed_head                  = 0b43ec291bdf28b47bdaa7e2e99a66c97d4716c6
reviewed_response              = docs/task036_forward_solver_bugfix_hardening/response_v5.md
ordinary_default               = unchanged
master_merge                   = not_authorized
current_modal_M120_M240        = controlled_negative_as_global_interface_space
current_exact_FE_trace_chain   = development_equivalence_pass / research_oracle
current_0p7nm_scalability      = fail
next_program                   = compress_the_exact_trace_chain_without_losing_observables
iterative_solver               = deferred_in_this_batch
wavelength_continuation        = deferred_in_this_batch
broad_parameter_scan           = paused
final_response_document        = required
```

本 Review 接受最新结果中最重要的数值事实：

1. **P 偏振和小掠射角并不是 Hybrid 域分解天然不能处理。**
2. 旧 `M120/M240 physical-QEP` 接口空间不完整，无法携带完整的 Maxwell joint-Cauchy
   信息，因此在 residual 很小的情况下仍会丢失部分衍射复振幅。
3. 用每个平面完整的 `1200` 维有限元切向 trace、逐层 exact Schur chain 和块三对角
   direct LU，可以在同一离散下把 Full3D observable 恢复到机器精度。
4. 但这一成功依赖**取消接口降阶**，只能证明域分解和 Schur 链正确，不能证明原来的
   低维 modal Hybrid 已经修好，更不能证明它可以扩展到 `0.7 nm / 2 TB`。

因此当前成果必须重新命名和分层：

```text
physical_QEP_modal_Hybrid_M120_M240
    = controlled negative for robust full-channel production

exact_FE_trace_chain_direct
    = development equivalence pass / exact reduced-domain oracle

scalable_low-rank_Hybrid
    = not implemented
```

下一阶段不继续优化现有 13,200-row dense-block direct 路径，也不立即开始迭代法。
唯一任务是：**利用 exact trace-chain 作为老师算子，找到远低于 1200 维、仍能完整保持
joint-Cauchy 和所有衍射通道的端口表示。**

---

## 2. 对最新结果的实质审阅

### 2.1 真正成功的部分

在 A007-P 同源码对照中，最新 exact trace-chain 与 Full3D direct 已达到：

```text
channels                         = 80/80
Hybrid true residual             = 7.44e-14
max outgoing complex amplitude Δ = 4.01e-13
ΔR                               = 8.00e-14
ΔT                               = 7.53e-15
ΔA_volume                        = 5.70e-13
Hybrid process-tree peak         = 7.705 GiB
Full3D process-tree peak         = 9.398 GiB
Hybrid external wall             = 125.003 s
Full3D external wall             = 134.524 s
swap                             = 0
```

另外四个冻结 P 偏振角度点也完成了完整通道闭合。这说明：

```text
Hybrid domain decomposition           = mathematically viable
small-grazing P physics                = viable
endpoint sign / DtN / recovery         = viable after fixes
old failure root                      = truncated interface space
```

这是一项真正的正确性突破，应当保留。

### 2.2 不能被夸大的部分

最新方法的正式未知量不是 `M120 + M120`，而是：

```text
11 trace planes × 1200 FE trace coordinates = 13,200 rows
```

每个 z-cell 通过完整的 `1200 × 1200` Schur blocks连接。显式 trace-chain AIJ 的 measured
NNZ 为：

```text
44,640,000
```

而同输入 Full3D static matrix 为：

```text
26,952,096 NNZ
```

行数虽然减少，但 Schur blocks 变稠密，矩阵 NNZ 反而增加。最终峰值只比 Full3D低约
18%，远低于原始 Hybrid 希望取得的数量级压缩。

代码当前还具有明显研究实现特征：

- `FullFeTraceChainAction` 固定 `cell_count == 10`；
- block LU 的 MPI 路径仍由 root factor，再广播完整 dense factors和solution；
- 综合 runner约六千余行，混合了实验调度、数据转换、审计、求解和后处理；
- 数值 authority来自 dirty development source identity，而不是 clean committed source；
- full repository pytest、CI和 clean-source formal rerun 尚未完成。

因此不得写成：

```text
modal Hybrid production pass
0.7 nm route solved
```

更不能整体合并该分支。

---

## 3. M120 / M240 接口降阶空间还能否成功？

### 3.1 作为“固定全局接口空间”：我判断成功概率低

已有证据非常一致：

- A007-P 的 M120 为 `51/80`，M240仅为 `52/80`；
- M120→M240 对主要振幅、能量缺口几乎没有方向性改善；
- M240峰值已从约5.57 GiB增至7.50 GiB；
- 以前的 M480/M492 进一步失去资源优势；
- transfer-optimal capacity在冻结的 rank≤240预算内没有达到 tail Gate；
- exact joint-Cauchy审计表明，旧接口缺口主要位于完整 Cauchy 数据，而不是 selected
  M120 core内部传播错误。

因此：

```text
继续沿相同 physical-QEP family 只把 M 从120提高到240、320、480
```

不是值得继续的主路线。它很可能在精度达到之前先失去内存优势。

### 3.2 作为“长中间区 core basis”：M120仍然有价值

不能因此把 M120全部废弃。one-cell和exact port-operator审计已经证明：

```text
inside selected M120 space,
scalar-CG propagation/operator error ≈ 2e-11
```

也就是说，M120适合表示远离端部边界层的长程传播空间。真正失败的是让同一组 M120
同时承担：

```text
long-range propagating core
+
endpoint evanescent / boundary-layer joint-Cauchy content
```

正确方向应是：

```text
M120 core负责长距离传播
+
局部、可凝聚的端部corrector负责接口近场
```

所以我的结论是：

> **M120/M240 作为独立、全局的接口降阶空间不太可能成为稳健生产方案；M120作为长中间区
> core，在端部增加另一种局部 Cauchy-complete corrector 后仍很有希望。**

---

## 4. 如何既修复接口空间，又保留 Hybrid 优势？

### 4.1 首选架构：localized full-trace boundary corrector + M120 core

最新 exact trace-chain 已经提供了一个可用的老师算子。最直接的压缩方法不是把11个平面
都降成 M120，而是只在端部短边界层保留完整 trace：

```text
bottom exact buffer : z = 10,20,30（必要时到40）
core modal region   : z = 30...90（或40...80），使用M120
 top exact buffer   : z = 90,100,110（必要时从80开始）
```

关键区别是：这些 full-trace buffer **不能像30/90、40/80旧模型那样作为全局3D端帽未知量
全部保留**。它们必须在局部组件内部做二级Schur凝聚：

```text
endcap volume + short exact-trace buffer
    ↓ local component condensation
M120 core-facing port + external DtN coordinates
```

这样可以同时做到：

- `z=10/110` 处的真实电场/traction近场由完整FE trace表示；
- 边界层衰减后，再投影到已经证明健康的M120 core；
- full 1200-dim planes只在局部factor/materialization阶段存在；
- 全局未知量仍接近 `2M + external auxiliaries`，而不是13,200；
- endpoint buffer可以顺序处理和释放，不与全局solve同时驻留。

这是当前最符合证据、也最有机会保留原Hybrid优势的路线。

### 4.2 端部corrector的压缩方式

局部buffer本身也不能永久保留完整1200维。应按下列优先级压缩：

#### A. full-interface discrete Bloch modes

直接从真实one-cell Schur/Bloch问题求离散传播/倏逝模式，而不是只使用二维连续QEP模式。
它天然匹配：

- 同一3D Nédélec离散；
- 同一p/h和Floquet orientation；
- joint electric/traction trace；
- lossy、non-Hermitian和near-degenerate情况。

其用途不是替换健康的M120 core，而是构造端部短程corrector。

#### B. RCWA Fourier/layer modes

对当前垂直矩形、z分层和规则周期结构，RCWA是非常有竞争力的端部/中间基底。用户现有
RCWA报告在同一 `50×25 nm` 周期、`17×120 nm` 条纹几何下，0.7 nm使用
`(ku,kv)=(11,11)` 时 `R_total/T_total/R00/T00` 已表现稳定，峰值工作集约2.66 GB。
这说明 Fourier/layer basis 的压缩潜力很大。

但现有报告只资格化四个总量/零级指标，且角度为80°/0°，不能直接证明当前96-channel、
复振幅和joint-Cauchy合同。正确用法是：

```text
exact FE trace-chain作为老师算子
→ 把RCWA Fourier/layer modes投影到同一FE trace/Cauchy metric
→ 同rank比较port-operator和全通道误差
```

若RCWA basis在远低于1200维时通过，它可用于：

- 整个规则结构的独立RCWA前向求解；或
- FEM endcap + RCWA middle/buffer的混合求解。

后者仍需要接口投影，但可以用 exact trace-chain直接资格化，而不是只看R/T总量。

#### C. transfer-optimal / POD basis，但必须改变source定义

前一轮 rank≤240 transfer capacity negative不能被解释为所有optimal-port方法失败。它更像是：

```text
在冻结的worst-case source/metric和rank预算下，尾部没有足够快衰减。
```

如果再次研究，source space必须限定为真实可达物理输入族，例如：

- external incoming diffraction channels；
-冻结的角度/偏振/几何参数邻域；
- endcap residual和material perturbation loads；
- 需要保真的完整observable contract。

不能要求一个小basis以 `1e-8` 逼近整个任意1200维Cauchy source空间，那会把真正可压缩的
物理流形与最坏情况全空间混为一谈。

#### D. hierarchical low-rank compression of Schur blocks

若找不到很低维的port basis，也不代表只能保存1200×1200 dense blocks。可以审计：

- HSS/HODLR/H-matrix；
- randomized block low-rank；
- physically ordered edge/face clusters；
- Fourier preconditioned compression。

但高频Maxwell的off-diagonal rank可能随波长增长，因此必须先测谱，不得先搭通用H-matrix
框架。

---

## 5. Review V6批准的下一批工作

### Stage V6-0：冻结 exact trace-chain oracle，不再继续优化其direct性能

先完成一次 clean-source最小资格化：

```text
A007-P p5/h10     # 复现最新主点
A004-S p5/h10     # 原最难S点，96-channel
nominal p6/h10    # frozen 59-goal authority
```

要求：

- 从最新clean commit运行；
- fixed BLAS/OpenMP threads和CPU affinity；
-正式process-tree watchdog；
- zero swap；
- 提交compact JSON/CSV，不提交heavy artifacts；
- focused suite + full repository pytest + Ruff + compileall + diff-check。

如果clean-source不能复现，先修identity/runtime问题，不进入压缩研究。

### Stage V6-1：同rank端口空间容量对照，禁止新forward PDE

利用exact trace-chain和Full3D frozen traces，在完全相同的joint-Cauchy metric下比较：

```text
B0 = current physical-QEP modes
B1 = full-interface discrete Bloch modes
B2 = RCWA Fourier/layer modes
B3 = transfer/POD modes on frozen reachable source manifold
```

这是有界的**离线容量比较**，不是四条同时开发的production solver。每种basis只需完成
trace映射和operator projection；没有资格化结果前不得写正式forward path。

冻结rank：

```text
120, 240, 360, 480
```

对每种basis和rank报告：

- bottom/top electric、traction、joint-Cauchy best approximation；
- 11 planes最大和aggregate residual；
- exact trace-chain projected operator error；
- 96/80/59-goal observable replay error；
- Gram/inf-sup/near-degenerate identity；
- predicted rows、NNZ和peak；
- mode generation/storage cost。

#### 容量通过条件

至少有一种basis在：

```text
rank <= 360 per directional pair / equivalent port dimension
joint-Cauchy max residual <= 1e-8
projected exact-operator error <= 1e-8
all frozen channel/goal replay pass
predicted whole-job peak <= 0.70 * Full3D
```

下通过，才授权实现actual reduced Hybrid。

若所有basis都需要接近完整1200维，则必须诚实记录：

```text
LOW_RANK_INTERFACE_COMPRESSION_NOT_DEMONSTRATED_AT_13P5NM
```

不能继续把rank提高到接近full trace后仍称为降阶成功。

### Stage V6-2：优先实现 localized-buffer + best basis

V6-1通过后，只实现一个候选：

```text
exact/full boundary buffer in local component
+
best qualified low-rank core-facing basis
+
M120 long-range core
```

不得同时实现多种basis或自动选择器。

实现要求：

- full-trace planes只在local component condensation内存在；
- global unknowns不包含所有11×1200 trace rows；
- 不形成长期resident global1200² blocks；
- bottom/top buffer顺序或并行分组处理后立即释放factor；
- global系统必须保持明显小于Full3D；
- actual接口仍恢复到10/110 nm；
- M120只负责已证明健康的long-range core。

### Stage V6-3：只运行一个actual anchor

第一点固定为：

```text
A004-S, p5/h10, Ny4, 0.5° grazing, 45° azimuth, MPI8
```

必须同时达到：

```text
96/96 channels
energy closure <= 1e-5
max ΔR/T/A_volume vs Full3D <= 1e-4
true residual <= 1e-9
joint-Cauchy / Petrov / DtN / Floquet pass
zero swap
whole-job peak <= 0.70 * Full3D
external wall <= Full3D
```

通过后才运行A007-P作为P偏振确认；失败则停止，不调rank、不换basis、不修改Gate。

---

## 6. 对RCWA路线的明确要求

RCWA可以进入V6-1的basis比较，但必须满足以下约束：

1. 使用与A004-S/Full3D完全相同的波长、角度、方位、S/P、材料和几何；
2. 不只看`R_total/T_total/R00/T00`；必须导出完整通道复振幅和joint E/H trace；
3. 使用稳定S-matrix，不使用会放大evanescent逆传播的普通transfer matrix；
4. Fourier harmonics必须映射到同一FE trace mass与Cauchy metric；
5. 截断收敛必须由完整通道、operator和Cauchy误差判定；
6. 若完整RCWA本身已经在规则几何上低资源通过全部合同，应允许它成为该几何的独立
   production/reference solver，不必为了统一形式强行保留FEM-RCWA接口。

现有RCWA三波长报告只作为强正信号，不作为V6资格化authority。

---

## 7. 明确禁止的工作

本批次禁止：

```text
继续优化13,200-row exact trace direct LU
把Full3D trace-chain改成大型通用framework
继续M120→M240→M480 heavy PDE sweep
恢复226点参数扫描
开始FGMRES/PC
开始h/p
开始波长continuation
开始代理模型和反演
修改ordinary default
整体merge Task036分支
```

没有低秩容量证据前，不得用“以后可迭代化”掩盖当前接口空间仍接近full trace的问题。

---

## 8. 代码与合并处置

### 8.1 可保留的研究能力

```text
src/solvers/hybrid_trace_chain.py
src/solvers/hybrid_local_dtn.py 中的one-sided Schur/action能力
exact trace-chain相关tiny/MPI tests
P投影、traction、beta、Floquet和DtN通用bugfix
```

其中exact trace-chain必须标记为：

```text
research_oracle / explicit opt-in
```

### 8.2 不得原样进入master

```text
benchmarks/run_task036_transfer_optimal_port_capacity.py  # 巨型综合研究runner
Task-local dirty-probe调度逻辑
硬编码10-cell/1200-row的production入口
大量一次性artifact转换和审计代码
未经clean qualification的ordinary default改动
```

通用bugfix、research oracle和task-local runner必须分开选择性整合；Task036分支整体merge
不获授权。

---

## 9. 要求Codex最终返回的response

本轮结束前必须创建：

```text
docs/task036_forward_solver_bugfix_hardening/response_v6.md
```

必须用通俗语言回答：

1. clean-source exact trace-chain是否复现；
2. M120/M240为什么失败、M120 core为什么仍保留；
3. B0–B3同rank容量表；
4. 哪种basis在何种rank首次通过，或是否全部失败；
5. RCWA basis是否能在严格完整合同下压缩接口；
6. localized-buffer方案如何避免11个full-trace planes进入全局系统；
7. actual A004-S是否运行、是否通过；
8. rows、NNZ、wall、RSS/PSS/USS、swap及相对Full3D收益；
9. 当前能力应命名为modal Hybrid、trace-chain oracle还是其他；
10. 下一步唯一建议。

最终聊天报告还必须给出：

- final HEAD；
- numerical source identity；
- 修改文件；
- tests；
- actual PDE列表；
- 未运行项；
- working-tree状态；
- 与远程同名分支ahead/behind；
- master未修改、未合并的确认。

---

## 10. 最终审阅结论

```text
exact FE trace-chain correctness      = major pass
small-grazing / P domain decomposition = pass
physical-QEP M120/M240 global port     = controlled negative
M120 long-range core                   = retain
low-rank interface correction          = unresolved
0.7 nm scalability                     = not solved
```

最有希望保留原Hybrid优势的路线不是继续增加M，也不是把完整FE trace链直接放大，而是：

```text
exact local boundary-layer treatment
+ low-rank Cauchy-complete core-facing port
+ M120 long-range modal core
```

候选basis应由 exact trace-chain公平比较，优先审计 discrete Bloch 和 RCWA/Fourier modes；
transfer/POD只能在真实可达source manifold上重新评价。只有在远低于1200维时通过全部
operator和observable合同，才算真正解决接口空间问题。

---

## 11. 对 `reply_review_report_v6.md` 的二次审阅与强制修订

### 11.1 总体处置

```text
reply_disposition                         = ACCEPTED_WITH_MATERIAL_CORRECTIONS
localized_condensation_equivalence_issue = accepted_and_binding
rank_normalization                       = accepted_and_binding
B0_B1_Binfinity_first_batch               = accepted
RCWA_current_batch                        = deferred_but_not_rejected
clean_A007_only                           = conditionally_accepted
R1_capacity_semantics                     = revised_below
resource_gate                             = split_into_physics_and_engineering
hard_source_line_limit                    = rejected_as_formal_gate
```

Codex 的回复不是单纯“反驳 Review”，而是指出了原 V6 中一个真实且重要的代数漏洞：
**若 exact buffer 最终仍精确凝聚到与历史 `30/90`、`40/80` 完全相同的 M120 retained
coordinates，那么它与历史负模型代数等价，只能改变存储和生命周期，不能改变物理解。**
这一点必须接受，且原第4.1节不得被单独当作物理修复方案。

回复对 `M120 per direction = 240 primal columns per side` 的统一口径也是正确的。后续所有
rank、unknown、left-test和内存比较必须使用明确字段，不能再把单方向 M、双向 primal列数、
joint-Cauchy状态维数和left/Petrov列数混称为“rank”。

回复把首批比较收窄为 `B0/B1/B∞`，避免同时建设 discrete Bloch、RCWA、POD和层次矩阵
四条路线，符合当前效率要求。首批重点验证与 exact one-cell FE/Schur 离散一致的 B1，是
合理的最小研究问题。

但回复仍有若干地方需要实质修正，不能全盘照收。

### 11.2 R0只clean复现A007的适用边界

先clean复现A007-P可以确认 exact trace-chain 最新提交、CPU绑定、watchdog和资源口径没有
依赖 dirty worktree，因此作为最小R0是合理的。

但 R1 的容量判定主要面向 A004-S 等困难输入。旧 A004-S Full3D/exact-trace artifact 只有在
以下条件满足时才能作为R1老师解继续复用：

```text
current clean numerical-kernel blob identity
    == artifact numerical-kernel blob identity

mesh / p / Ny / material / wavelength / Bloch phase / DtN / postprocess identity
    == frozen authority identity
```

不能只因为A007 clean pass，就默认所有旧A004 artifact已被clean-source重新资格化。若任一
numerical kernel或observable定义发生变化，必须在R1前补一次clean A004 exact-oracle；这不是
恢复广域PDE扫描，而是保证容量老师解与当前代码一致。

因此：

```text
R0 clean A007 = minimum reproduction Gate
A004 clean rerun = conditional on kernel/artifact identity, not permanently forbidden
```

p6动态trace泛化继续延期是合理的。

### 11.3 R1必须区分“任意全迹空间”与“物理可达流形”

回复已经提醒 reachable-source 与 worst-case full-space metric不能混写，但当前主Gate仍可能
被理解为要求 `d_port<=360` 对任意1200维Cauchy source都达到统一 `1e-8`。这对低秩物理
端口空间可能是不必要、甚至原则上不可能的要求。

R1必须并列维护两个不同结论：

```text
uniform_full_trace_diagnostic
    = 对任意数学trace方向的最坏情况谱尾；只作可压缩性上界诊断

reachable_physics_gate
    = 对预先冻结的物理source manifold、参数切向载荷和独立holdout输入的正式Gate
```

正式低秩资格化应基于：

- 预先冻结的external incoming diffraction channels；
- 预先冻结的S/P、掠射角、方位角和几何参数切向载荷；
- 必要的material/endcap residual loads；
- 与basis构造完全隔离的holdout anchors。

若 full-space uniform tail不通过、但reachable manifold与独立holdout全部通过，只能写：

```text
physics-manifold compression pass
uniform arbitrary-trace compression not demonstrated
```

不能把前者升级为任意输入production pass，也不能用后者否定一个对实际服务输入有效的空间。

反过来，若basis直接吸收某个Full3D solution snapshot，再用同一个snapshot验证，就没有独立
证据。回复提出capacity/holdout隔离是正确的，必须落实到文件和数据身份，而不是只写原则。

### 11.4 observable replay必须是真正的reduced solve

R1中的“all frozen holdout channel/goal replay”不能通过以下方式完成：

```text
把Full3D老师解正交投影到candidate basis
→ 直接从投影场计算通道
```

这种做法只能证明最佳逼近能力，会系统性高估实际Galerkin/Petrov求解器的性能。

正式replay必须：

1. 从basis和exact trace-chain operator形成冻结的reduced trial/test operator；
2. 使用独立的physical RHS在reduced operator上求解；
3. 从reduced solution独立恢复observable；
4. 与未参与basis/rank选择的holdout Full3D/exact-oracle比较。

最佳逼近误差可以保留为capacity diagnostic，但不能代替reduced-solve observable Gate。

### 11.5 B1 discrete-Bloch的实现边界

B1是当前最合理的第一候选，但它不是天然成功，也不是未来0.7 nm可扩展性的证明。

当前尺度的B1必须：

- 使用同一one-cell FE/Schur离散；
- 保持forward/backward、reciprocal和near-degenerate connected blocks整体；
- 不为了恰好得到`280/320/360`列而拆开认证块；
- 使用稳定的two-sided scattering、ordered QZ/Schur或等价passive classification；
- 禁止通过growing inverse factors传播强倏逝模式；
- 明确它是当前p5/h10离线basis generator，不把完整1200/2400维dense eigenproblem包装成
  0.7 nm可扩展实现。

因此冻结维数 `240/280/320/360` 是目标上限，不是必须精确命中的数字。若reciprocal或
near-degenerate block closure要求向上取整，应报告：

```text
requested_dimension
effective_block_closed_dimension
```

且所有同维比较使用effective dimension。

若B1在有效维数不超过360时失败，正式结论只能是：

```text
DISCRETE_BLOCH_LOW_RANK_NOT_DEMONSTRATED_IN_THIS_BATCH
```

不能由此直接推出所有RCWA、reachable-source transfer/POD或其他低秩接口表示都不可能。

### 11.6 anti-equivalence Gate：非零修正是必要条件，不是充分条件

回复要求报告 `ΔK_corr` 并证明candidate不等价于历史30/90、40/80负模型，这一点正确。
但仅有：

```text
||ΔK_corr|| > numerical_noise
```

不能获得物理credit。一个非零修正也可能让exact-action和observable更差。

必须同时满足：

```text
candidate exact-operator error
    < old 30/90 error
    and < old 40/80 error

candidate joint-Cauchy error
    < old 30/90 error
    and < old 40/80 error

independent holdout reduced-solve observables
    improve in the frozen metric
```

rank前缀的误差趋势应完整报告，但由于lossy Petrov空间不保证每个单目标严格单调，不能把
“每一级都单调”设为硬数学Gate。最终冻结rank必须由预先定义的综合合同决定。

### 11.7 资源Gate应与物理容量Gate分开

回复将：

```text
predicted_peak + uncertainty <= 0.70 * Full3D
```

作为actual implementation的统一前置条件，工程目标明确，但作为数学容量结论过于刚性。
建议分为：

```text
physics_compression_pass
    joint-Cauchy/operator/holdout observables全部通过

engineering_auto_authorize
    predicted_peak_upper <= 0.70 * Full3D

engineering_review_zone
    0.70 * Full3D < predicted_peak_upper <= 0.80 * Full3D

no_meaningful_advantage
    predicted_peak_upper > 0.80 * Full3D
```

- `<=0.70`：可以自动进入R2；
- `0.70–0.80`：不得自动运行actual，但也不得把低秩数学结果写成失败，应停下来review是否
  还有明确的生命周期/缓存常数可去除；
- `>0.80`：对当前13.5 nm直接法没有足够工程优势，不进入actual。

这一区分避免用一个资源目标抹掉有价值的数学结论，同时也防止以“以后还能优化”为理由把
接近Full3D的方案包装成Hybrid成功。

### 11.8 wall time必须区分cold与warm

对于后续代理模型、参数反演和角度扫描，basis/QEP生成可能被多个RHS或邻近参数点摊销。
因此 `external wall <= Full3D` 不能只比较一次cold全过程。

必须至少报告：

```text
cold_setup_wall
warm_repeated_solve_wall
basis/cache_build_wall
cache_identity_and_invalidation
```

正式R3物理资格化不因一次cold setup略慢而失败；工程目标应优先要求：

```text
warm_repeated_solve_wall <= Full3D repeated_solve_wall
```

若只能单次运行，则同时给出含/不含一次性basis生成的两个口径，不得选择性引用较好数字。

### 11.9 不接受以代码行数作为正式停止Gate

回复提出“首个action fixture前新增超过约500行非测试代码就停止”。这可以作为提醒，但不能
成为正式数值Gate。必要的orientation、left/right、Schur和non-Hermitian实现有时确实超过
任意行数阈值。

正式限制应改为scope-based：

- 不新增generic framework、campaign、scheduler、fallback和自动调参；
- 每个新增模块必须职责单一；
- 若需要同时重写mode generation、coupling和global solver三个架构层，则停止review；
- 若只是在一个已批准数值层中实现完整而必要的算法，不因行数机械停止。

代码规模必须报告，但行数不是物理正确性的替代指标。

### 11.10 RCWA延期是合理的，但不能被路线性否定

当前批次不实现RCWA是合理的：Task036分支没有绑定Lumerical工程、脚本、raw complex
channel amplitudes和joint E/H trace，无法与B0/B1做同一authority比较。

用户现有RCWA报告只监测`R_total、T_total、R00、T00`，输入为`theta=80°、phi=0°`；同时
几何在y方向均匀，报告明确说明kv扫描不改变功率。因此它是规则近一维条纹下的强正信号，
不是generic 3D接口basis已经通过的证据。

若B1失败，下一轮review仍应保留两条候选：

```text
independent full-RCWA qualification on the exact A004/A007 contract
reachable-source transfer/POD with strict holdout separation
```

不能因为本批收窄为B1，就在战略上把RCWA永久删除。

### 11.11 修订后的执行矩阵

| 阶段 | 修订决定 |
|---|---|
| R0 clean A007-P | 批准；同时完成A004旧authority的kernel/artifact identity审计 |
| clean A004 oracle | 仅在identity不等价时必跑；等价时复用 |
| R1 B0/B1/B∞ | 批准；effective dimensions按reciprocal/near-degenerate block闭合 |
| full-space tail | diagnostic，不替代reachable-physics Gate |
| holdout observable | 必须由独立reduced solve得到，不允许teacher-solution投影冒充 |
| B1 d_port<=360 pass且peak<=0.70 | 自动解锁R2 |
| B1 physics pass但peak在0.70–0.80 | 停止并review，不自动actual |
| B1 peak>0.80或physics fail | 本批停止；不得增rank |
| R2 localized candidate | 必须含真实`R_corr`和可测`ΔK_corr`，不能只是Schur重写 |
| R3 A004-S | 仍为第一个actual reduced anchor |
| A007-P confirmation | 仅在A004-S全部Gate通过后运行 |
| RCWA/POD/p6/iterative | 当前批次延期；不是永久否决 |

### 11.12 对Codex下一步的最终指令

Codex应以 `reply_review_report_v6.md` 的收窄路线为主体，并以上述11.2–11.11修正为最终执行
边界。当前不得直接实现actual candidate。

下一步只做：

```text
R0 clean A007 exact-oracle reproduction
+
A004 frozen authority numerical-kernel identity audit
+
R1 B0/B1/B∞ bounded offline capacity
```

R1结束后必须先提交并推送：

```text
docs/task036_forward_solver_bugfix_hardening/response_v6.md
```

随后停止等待review。除非R1同时达到physics Gate与`<=0.70 Full3D`的auto-authorize Gate，
本批不进入R2/R3；即使达到，也应先在response中明确列出effective rank、anti-equivalence、
reduced-solve holdout、cold/warm资源模型和修改规模，再按既有授权执行单一candidate。

最终状态不得提前写成compressed Hybrid pass。