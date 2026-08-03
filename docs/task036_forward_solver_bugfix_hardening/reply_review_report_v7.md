# Task036 Reply to Review V7：同意一次有留出集的可达源容量实验，并冻结执行口径

## 0. 文档身份

```text
document                         = Task036 Reply to Review Report V7
reviewed_review                  = review_report_v7.md
reviewed_review_commit           = 2ab2b5ee0fc68d9b2f343c6469f81ecde88028c1
branch                           = codex/20260730-task36-forward-solver-bugfix-hardening
decision                         = AGREE_WITH_BINDING_CLARIFICATIONS
implementation_by_this_reply     = not_started
new_forward_PDE                  = not_run
C1b_teacher                      = not_run
C1c_reduced_solve                = locked
iterative_solver                 = forbidden_and_not_run
ordinary_default                 = unchanged
master_merge                     = not_authorized
```

本文回应 `review_report_v7.md`。总体上同意 V7：B1 应以受控负结果关闭；C1a 应准确命名为
`paired_two_end_reachable_response_POD`；下一步只值得做一次预冻结 `80 capacity + 16 holdout`
的 96-RHS exact teacher，以回答当前真实可达响应是否能在 `r<=80` 内压缩。

本回复不实现 C1b、不启动 PDE，也不解锁 C1c。以下澄清主要防止把训练投影、同算子留出集、
离线教师资源或 minimum-residual 诊断写成已经修复的 compressed Hybrid。

---

## 1. 结论先行

| V7 事项 | 回复决定 | 约束或说明 |
|---|---|---|
| 冻结 B1 `d<=360` | 同意 | 保留 compact 负结果，不再追加 v9、rank 或阈值 |
| C1a research checkpoint | 同意 | 是两端共享系数的全局响应 POD，不是两个局部 corrector |
| 一次 96-RHS exact teacher | 同意 | 只允许一次 watchdog 数值运行，无 retry |
| 预冻结 `80/16` | 同意 | 必须从现有 builder 的真实通道身份生成并在看谱前入 Git |
| `r=0/20/40/60/80` | 同意 | 同一 teacher、同一 split、同一最大谱只读 prefix |
| same-operator holdout | 同意但限名 | 只能证明 source-family 泛化，不能称跨算子或物理 production holdout |
| `||KX_r-B||/||B||` | 同意但需定口径 | `X_r` 必须是完整 11-plane trial response；不得只算 endpoint 残差 |
| C1b pass | 同意但限名 | 只能写 `pass_on_frozen_same_operator_source_holdout` |
| minimum-residual QR | 原则同意，继续锁定 | 必须使用与显式残差一致的复数内积/度量 |
| periodic-gauge pullback | 原则同意，继续锁定 | 需要 primal/dual 配对保持；不进入本轮实现 |
| `10 GiB / 7200 s` | 同意为 safety cap | 不是最终 compressed Hybrid 的工程通过指标 |
| p6、0.7 nm、RCWA、iterative | 不批准本轮 | 保持 V7 锁定 |

因此 V7 可以作为 C1b 的上位授权，但实际执行必须遵守第 3--7 节的绑定解释。

---

## 2. 对 V7 主要判断的同意

### 2.1 B1 已经足够回答当前问题

B1 v4 在总端口维数 `d<=360` 时的最优 trial 残差仍约为 `8.9e-5`，继续扩大同类
discrete-Bloch v9 空间的边际收益不足。接受：

```text
B1_discrete_Bloch_d_le_360 = controlled_negative / closed
```

后续只补一个 task-local compact record，绑定既有 raw artifact、SHA 和原始 Gate；不重跑 B1，
不新增通用 schema、receipt framework 或 campaign。

### 2.2 C1a 的命名纠正正确

现有 C1a 使用 bottom/top 响应的共享 source coefficient。它描述的是同一物理激励在两端以及
完整 trace 链上的成对全局响应，不能称为两个可独立释放的 localized endpoint corrector。

冻结名称：

```text
paired_two_end_reachable_response_POD
```

这一路线的直接问题只是：真实 96 列可达响应在扣除 M120 core 后是否还有低秩结构。C1b 应
只回答这个容量问题，不同时开发 test space、actual reduced solver 或新物理算法。

### 2.3 V7 对 `r=96` 训练闭合的警惕正确

若用全部 96 个 teacher columns 建基，再在同一 96 列上评价，`r=96` 对所选 snapshot/output
span 的舍入级闭合基本是线性代数恒等结果，不构成压缩证据。这里的“必然闭合”只适用于
被建基的 snapshot/output span；若完整 harmonic extension 或 operator action 另有近似，不能
自动外推为 full-chain residual 也闭合。

因此同意预冻结 `80/16`，并把 16 列完全排除在 Gram、POD eigenvectors、rank 选择和任何
运行后调参之外。

---

## 3. 绑定澄清一：96 个 source identity 与 `80/16` split

### 3.1 `S/P` 的实际含义

代码核对表明，`build_hybrid_local_incoming_load_columns()` 每侧从现有 `PortMode3D` 顺序生成
48 个 incoming companions；每列天然带有：

```text
(side, m, n, polarization)
```

其中 `polarization` 是端口通道的代码值 `s` 或 `p`。bottom/top 合并后为 96 个物理 RHS。
V7 的 source identity 因而可直接由现有 builder 元数据生成，不需要发明新的通道系统。

需要明确区分：

- `A004-S` 中的 `S` 是冻结算例的名义入射偏振标签；
- 96-RHS teacher 是对冻结算子的物理 incoming channel family 取列，其中同时包含端口
  `s` 和 `p` 通道；
- 文档中的 “S/P 均有 holdout” 应解释为 builder 的通道 `polarization in {s,p}`，不能误写成
  已经运行两个独立 A004-S/A004-P 算子。

### 3.2 split 的冻结方法

运行前只增加一个小型、task-local 的 source table，例如：

```text
docs/task036_forward_solver_bugfix_hardening/outcomes/c1b_source_split.json
```

该文件至少包含：

- 96 个列号及 `(incident_side, m, n, polarization)`；
- 每列的 `capacity` 或 `holdout` 标签；
- 明确、确定性的选择规则；
- source list hash 和生成该列表的源码 SHA；
- bottom/top、s/p、zero/nonzero order 的计数检查。

选择应按现有稳定通道顺序做确定性分层，不使用运行后 seed，不依据谱、误差或“困难列”重选。
在没有先读取真实 96 列清单前，不在本回复虚构每个 `(side, polarization)` 的具体列号。

### 3.3 holdout 能证明和不能证明什么

这 16 列是：

```text
same_operator_source_family_interpolation_holdout
```

它能排除“80 个输入直接生成 80 个基向量，再在同一 80 列上自证”的明显循环；但 96 列仍
来自同一个 A004-S frozen operator。即使通过，也不能写成跨角度、跨 Bloch phase、跨几何、
跨波长或跨离散的独立验证。

`r=80` 若 capacity residual 达到舍入误差，training/capacity 本身不获得信用；只有未参与建基的
16 列 holdout 以及完整 operator-action residual 同时通过，才可获得 V7 限定的同算子容量信用。
还必须报告 capacity residual matrix 的 effective rank、首次通过 rank 和相对 1200 维 trace 的
压缩比例，避免只报“通过”。

---

## 4. 绑定澄清二：C1b 的 `X_r`、best approximation 与 operator residual

### 4.1 `X_r` 必须是完整 trace trial response

V7 要求：

$$
\frac{\|KX_r-B\|}{\|B\|}.
$$

这里冻结为：

- `K` 是同一 frozen A004-S exact trace-chain 的完整算子 action；
- `B` 是对应 capacity 或 holdout 的完整 RHS columns；
- `X_r` 是 M120 core 加 paired two-end POD corrector 后，经现有 harmonic/global extension 得到的
  完整 11-plane response；
- 使用和 exact trace-chain true residual 一致的列顺序、复数 dtype、归一化与显式 action；
- bottom/top endpoint-only action、只在 joint-Cauchy output 上投影，或只报告 POD discarded energy，
  都不能替代该 full action residual。

必须对 capacity 和 holdout 分开给出 per-column maximum 与 aggregate，不能把一侧或少数差列
藏在整体 Frobenius norm 中。

### 4.2 C1b 仍不是 reduced solve

C1b 为了评估 trial capacity，可以用 teacher response 计算所选度量下的 best-approximation
coefficient，再构造 `X_r` 并测量 `KX_r-B`。该系数使用了 teacher solution，因此结果应命名为：

```text
teacher_informed_best_trial_action_residual
```

不得命名为：

```text
reduced_solve_residual
independent_Hybrid_solution
production_true_residual
```

endpoint electric、traction、joint-Cauchy、11-plane trace 若分别计算各自的数学最优下界，必须
说明它们是否使用同一组 coefficient。用于 C1b pass 的完整 action residual应绑定一个明确的
canonical coefficient construction，不能在每项指标之间挑选不同系数后拼成“同时通过”。

只有后续 C1c 从 `K`、trial basis 与 physical RHS 独立求出 coefficient，才开始回答 reduced direct
solve 是否成立；V7 正确地继续锁定了这一阶段。

---

## 5. 绑定澄清三：资源 cap 不等于工程通过

同意单次 C1b teacher 的硬停止条件：

```text
external wall hard cap      = 7200 s
process-tree peak hard cap  = 10 GiB
swap                        = 0
retry                       = 0
```

但 `10 GiB / 7200 s` 只是一次性离线 teacher construction 的安全上限，不是对最终 compressed
Hybrid 的资源验收。它甚至高于当前同源 A007 exact Hybrid 的 `7.7046 GiB`，也略高于当前同源
Full3D 的 `9.3981 GiB`，所以不能被写成“Hybrid 资源优势通过”。

最终 direct compressed Hybrid 的整作业目标保持 `response_v6.md` 的口径：

```text
whole-job simultaneous peak <= 0.70 * same-input Full3D
whole-job external wall      <= same-input Full3D
swap                         = 0
```

C1b 必须分别报告 cold setup、factor、96-RHS solve、extraction/POD 的 wall 和 simultaneous
process-tree peak。`7200 s` 是 ceiling，不是预计耗时；不能把达到上限前仍运行称为进展，也不能
把分阶段对象体积相加冒充 simultaneous peak。

---

## 6. 建议的高效率执行分段

为了使“一次数值运行”真正只发生一次，同时避免边跑边改，建议相邻开发线程按以下三段执行；
监督线程只审阅 diff、测试和数值证据，不代替其开发。

### C1b-0：身份和负结果收口，不运行 PDE

1. 写入 B1 v4 compact record，建议路径：
   `docs/task036_forward_solver_bugfix_hardening/outcomes/b1_v4_compact_record.json`；
2. 从现有 builder 元数据生成并冻结 `c1b_source_split.json`；
3. 加 source-split contract test，证明 96 唯一列、80/16 数量及四类覆盖；
4. 提交并推送 Task36 分支，保证数值运行前 split 已有 Git identity。

这一段不新建 schema framework，不重跑 B1，不启动 teacher。

### C1b-1：纯实现与最小测试，不运行 PDE

只实现 C1b 所需的最小缺口：

- exact matrix-RHS teacher extraction；
- capacity-only paired two-end POD；
- frozen prefix evaluator；
- full 11-plane action residual与 compact record；
- watchdog negative path。

先运行 focused pure tests、touched-file Ruff lint、compileall 和 `git diff --check`。不得顺便开发
C1c、adjoint builder、跨角度 gauge、automatic rank tuner、retry/fallback、scheduler 或通用 evidence
framework。

### C1b-2：监督审阅后只运行一次

数值启动前由监督线程检查：

- source split 已在当前 HEAD 中冻结；
- `K/B/X_r` 口径与本文一致；
- 运行命令、artifact root、hard cap、进程组终止语义明确；
- 没有无关 defensive code；
- 环境、ABI、clean source 与 zero-swap preflight 通过。

随后相邻开发线程执行唯一一次 96-RHS run。正负结果均写入 `response_v7.md` 并停止，不因结果
接近阈值而重选 split、改 rank、放宽 Gate 或自动开始 C1c。

---

## 7. 对 C1c 与跨角度建议的保留意见

### 7.1 minimum-residual QR 原则同意，但必须绑定内积

V7 的 `Y=KR`、`Y=QT` 思路比 B1 中无物理依据的 Euclidean overlap 更合理。但对复数、
非 Hermitian 系统，`Q` 必须在用于定义显式 residual 的同一内积或 residual metric 下正交；
只有在该 metric 中，右端投影和三角方程才对应所声称的 minimum residual。

如果使用 metric `G`，应明确是通过可审计的 metric action/factor 实现 `G`-orthogonal QR，还是
先把 `Y` 与 `b` 映射到同一 whitened residual coordinates。不能一边用 Euclidean QR，一边用
physical metric 报告“最小残差”。这一点只冻结为下一轮设计要求，本回复不批准实现 C1c。

### 7.2 periodic-gauge pullback 原则同意，但当前不实施

同意不能直接堆叠不同 Bloch phase 的 1200 active coefficient。V7 提出的 original oriented
trace 展开、相位去除、有限元投影到 `k_t=0` canonical trace，再构造保持 pairing 的 dual map，
方向合理。

未来资格化时必须实测 mass pullback、roundtrip、orientation、corner phase 与
`q_k^H E_k = q_0^H E_0`。有限元乘相位再投影不是天然精确恒等，不能仅用逐自由度相位乘法
假定通过。该工作继续锁定，不得混入 C1b。

---

## 8. C1b 结果的允许表述

若存在 `r<=80` 通过 V7 全部冻结 Gate，可写：

```text
C1_primal_capacity = pass_on_frozen_same_operator_source_holdout
```

同时必须写：

```text
actual_compressed_Hybrid_solve = not_run
cross_operator_holdout         = not_run
Full3D_observable_equivalence  = not_run_for_compressed_candidate
engineering_memory_gate        = not_run
```

若 capacity 在 `r=80` 闭合而 holdout 不通过，接受 V7 的：

```text
SOURCE_SPAN_INTERPOLATION_ONLY
```

若所有 `r<=80` 均不通过，接受：

```text
REACHABLE_SOURCE_PRIMAL_COMPRESSION_NOT_DEMONSTRATED
```

两种负结果均关闭当前 C1，不追加 snapshot、不移动 holdout、不开发 C1c。正结果也只提交
`response_v7.md` 等待审阅，不自动运行 actual Hybrid、A007、p6、角度扫描或 0.7 nm。

---

## 9. 最终回复决定

```text
Review V7 strategic direction            = accepted
B1 d<=360                                 = controlled negative / closed
C1a naming                                = paired global response POD
C1b 96-RHS teacher                        = authorized once
C1b source split                          = frozen 80 capacity / 16 holdout
holdout credit                            = same-operator source-family only
C1b action residual                       = full 11-plane explicit action
C1b coefficients                          = teacher-informed / not a reduced solve
10 GiB and 7200 s                         = offline safety caps only
C1c minimum-residual QR                   = locked pending response_v7
cross-angle gauge map                     = locked
actual compressed direct Hybrid           = locked
p6 / 0.7 nm / RCWA / iterative            = locked
ordinary default                          = unchanged
master / PR                               = not authorized
```

综上，V7 值得执行，且比“用全部 96 列训练再自测”更有判别力。建议不再扩展讨论范围：先完成
C1b-0 的身份冻结与 compact record，再做最小实现审查，最后只运行一次 teacher。该实验应在
数小时安全上限内给出明确正负结论，而不是演化为新的长期防御框架或开放式算法开发。
