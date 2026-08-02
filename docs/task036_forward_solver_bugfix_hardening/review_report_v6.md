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
