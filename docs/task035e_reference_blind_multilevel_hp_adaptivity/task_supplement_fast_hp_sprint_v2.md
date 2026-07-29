# Task035e 补充任务书 V2：8 小时时间盒 h/p 快速迭代

## 0. 优先级与覆盖关系

本文件是 `task_supplement_fast_hp_sprint_v1.md` 的执行修订版。

V2 覆盖 V1 中以下内容：

- “最多 4 个 heavy PDE”的数量限制；
- 固定只执行 P2/P3/Hcheck/combined 四步的限制；
- 因 PDE 数量达到上限而停止的规则。

其余关于 59-goal、reference-visible development、数值 Gate、资源口径和禁止大型框架开发的原则继续有效。

本轮唯一目标是：

> 在约 8 小时内，尽可能多地复用现有求解器和 evaluator，跑出一条实际向收敛 reference 靠近、响应变化逐步减小的 h/p 序列。

本轮仍分类为：

```text
REFERENCE_VISIBLE_DEVELOPMENT_SPRINT
reference_blind_credit = false
```

---

## 1. 为什么取消 PDE 数量上限

现有 MPI8 实测表明，当前规模下单个 PDE 的典型耗时约为：

```text
current / full-p candidate    约 3.5–4.0 min
selected-p candidate          约 3.2–3.5 min
full-h candidate              约 6–7 min
```

随着 h/p 空间增大，单次耗时可能上升，因此不预设固定次数；但“4 个 PDE”明显不足以利用 8 小时时间盒。

新规则：

```text
不设 heavy PDE 硬数量上限
一次只运行一个 heavy PDE
以 8 小时时间盒、收敛趋势和停止条件控制总量
```

不得为了增加数量而随机扫描、重复同一 plan，或运行没有明确决策价值的模型。

---

## 2. 严禁大规模代码开发

### 2.1 允许

- 复用已有 runner、plan generator、variable-p/local-h solver 和 reference-visible evaluator；
- 修复阻断当前实验的明确 bug；
- 对现有 task-local helper 做小幅补充；
- 增加最小的 plan 去重、结果表格或循环调度逻辑。

### 2.2 禁止

- 新建 package；
- 新建 campaign/state-machine 框架；
- 新增 schema、receipt、watchdog、hash 层或 defensive wrapper；
- exact selected-action Schur/low-rank；
- 为本轮开发新的 hierarchical basis、p7 production 或 level-3 production；
- 重写已有求解器接口；
- 因文档、JSON排版或 checker 显示问题重跑 PDE。

### 2.3 代码预算

优先零代码。

如确有必要：

```text
最多一个 task-local helper
净新增建议 <= 300 行
不新增通用框架
```

同一个软件 blocker 若 30 分钟内不能用局部修复解决：

```text
保存 blocker
跳过该候选或切换另一条已有 lane
不得展开大重构
```

---

## 3. 起点

直接复用已经完成的 full p-shadow 作为：

```text
development current C1
```

理由：其相对 cycle0 current 的 59-goal normalized L2 true error 已降低 `27.120392%`，而 full h-shadow 只降低 `0.003046%`。

不得重新求 C1；直接复用其 plan、solution、59-goal outputs 和资源记录。

blind trial 历史保持不变；这只是 development ledger 的 current。

---

## 4. 动态 h/p 迭代流程

对 development current `Ck` 重复以下步骤，直到触发第 7 节停止条件。

### 4.1 优先尝试 broad/full p-enrichment

使用现有合法 p-shadow machinery 构造下一层 broad p candidate `Pk`：

- p 只允许 `{4,5,6}`；
- 不再选择 single-cell 或 four-cell tiny action；
- 不使用 cellwise DWR 数值预测 endpoint delta；
- inactive modes 不进入矩阵；
- exact sequence、Floquet、hanging、static condensation 保持现有 Gate；
- 同一 plan SHA 不得重复运行。

运行实际 MPI8 PDE，随后立即由 reference-visible evaluator计算：

```text
E2, Einf
power/amplitude/totals/fields 分类 E2/Einf
D2, Dinf（相对 Ck）
RSS/PSS/USS、rows、NNZ、factor、wall time
```

### 4.2 p candidate 接受规则

若同时满足：

```text
E2(Pk) < E2(Ck)
Einf(Pk) <= 1.05 * Einf(Ck)
totals E2 不恶化
所有数值/资源 Gate 通过
```

则接受：

```text
C(k+1) = Pk
```

candidate 已经求解完成，禁止重新作为 current 求一次。

若 `E2` 改善不足 1%，记录为 p-stagnation；连续两次 p-stagnation 或已无合法 p-up 时，切换到 h-check。

若 Pk 恶化，拒绝并立即对当前最优 current 做一次 h-check；不通过改变阈值或挑别的单 cell 反复调参。

### 4.3 h-check

只有以下任一情况才运行 h candidate：

- p lane 连续两次改善不足 1%；
- 已无合法 p4→p5 / p5→p6 broad enrichment；
- p candidate 明显恶化；
- p-surplus 衰减慢的区域占主导。

h candidate 必须复用现有 full h-shadow / multi-patch local-h machinery：

- 使用实际非均匀 local-h；
- 可一次标记一批区域，不局限单 cell；
- DWR、residual、projection surplus只用于 ranking；
- 不要求其精确预测 endpoint delta；
- 不新增 action-specific estimator。

接受规则与 p candidate相同。

### 4.4 p/h 交替

若 h candidate 被接受，则下一步重新尝试 broad p-enrichment。

若 p 与 h 都改善，允许按：

```text
p -> h -> p -> h
```

自然交替，不必另建 combined-action 框架。

只有现有工具能零/小代码生成 combined plan 时才可运行 combined candidate；否则不做。

---

## 5. “哪里改、用 h 还是 p”的依据

### 5.1 哪里需要处理

可使用：

- multi-goal DWR magnitude；
- strong/full residual；
- p4/p5/p6 projection surplus；
- 材料界面、周期和 2:1 closure。

它们只提供位置排序，不获得精确 action-response credit。

### 5.2 p 还是 h

优先使用已有相邻 p-level surplus 衰减：

```text
rho_K = eta_(p->p+1,K) / max(eta_(p-1->p,K), eps)
```

建议：

```text
rho_K <= 0.35  -> p-preferred
rho_K >= 0.60  -> h-preferred
中间区域       -> 由当前 full p/h lane 的实际结果决定
```

若现有代码不能直接给出 `rho_K`，不得为本轮重写 basis；继续用 broad p/h actual solves 决策。

---

## 6. 每次 PDE 后必须立刻决策

每个 PDE 完成后，在启动下一个 PDE 前必须生成一行追加记录：

```text
candidate_id / plan_sha
h/p type
leaves / p4-p5-p6
DoF / rows / matrix NNZ / factor NNZ
solver RSS / total RSS / swap / wall
E2 / Einf / D2 / Dinf
category E2
accepted or rejected
next action and reason
```

禁止在多个 PDE 全跑完后才统一分析。

禁止重复运行相同 plan 或已完成 candidate。

---

## 7. 停止条件（不再按 PDE 数量停止）

满足任一条件立即停止并收口：

1. 实际工作时间达到约 8 小时；
2. 剩余时间不足以安全完成“一个 PDE + evaluator + 提交”；
3. `59/59` 进入 reference tolerance；
4. 连续两个 accepted step 满足：

```text
D2 <= 0.5
Dinf <= 1.0
```

5. 连续两个 candidate 被拒绝；
6. p 与 h 两条 lane 均连续停滞；
7. 无新的合法 p/h plan；
8. 出现 OOM、swap、数值 Gate 失败；
9. 继续需要大规模代码/框架开发；
10. 同一 blocker 超过 30 分钟。

没有 PDE 数量上限，也不得因为“已经运行若干次”提前停止；同样不得为了用满 8 小时而无目的扫描。

---

## 8. 最终判断

用户对开发验证流程的理解基本正确：

```text
反复构造合法 h/p candidate
-> 实际求解
-> 响应变化逐渐减小
-> 冻结最佳 candidate
-> 与独立收敛 reference 比较
```

本轮报告必须明确区分：

- `response-stable`：相邻 accepted candidates 的输出变化已经很小；
- `reference-accurate`：与收敛 reference 的误差满足合同；
- `resource-efficient`：在达到精度后，rows/NNZ/factor/memory足够低。

本轮优先级仍为：

```text
跑通收敛路径
> 多做有判别力的 actual PDE
> 找到局部最优动作
> 完整 blind 认证
> 最小内存极限
```

---

## 9. 最终交付

停止后只提交：

- 一个结果 Markdown；
- 一个 compact JSON 或 CSV；
- 实际用到的 plan files；
- 至多一个小型 helper；
- 当前最佳 candidate 及完整 h/p 收敛序列。

不得在本轮末尾自动开启 Path B、Hybrid、迭代法、p7、level-3 或新的 task version。
