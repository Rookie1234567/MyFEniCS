# Task035e 补充任务书 V1：8 小时快速 h/p 收敛主线

## 0. 本补充任务的定位

本补充任务不替代原 `task.md`，只调整接下来约 8 小时的研发优先级。

当前已经确认：

- `cycle0 current` 可稳定求解；
- full `p-shadow` 相对收敛 reference 的 59-goal normalized L2 真误差降低 `27.120392%`；
- full `h-shadow` 只降低 `0.003046%`；
- single-cell 与 four-cell selected-p candidate 均恶化；
- 现有 cellwise DWR 可保留为位置排序信号，但不能继续当作 action-level 定量响应预测；
- 不再让 exact selected-action Schur、复杂 evidence schema 或新的自动驾驶框架阻塞主线。

本轮核心目标只有一个：

> 先用已有求解能力快速跑出一条确实向收敛解靠近的 h/p 序列，再讨论最小内存压缩和最终 reference-blind 认证。

本轮分类固定为：

```text
REFERENCE_VISIBLE_DEVELOPMENT_SPRINT
reference_blind_credit = false
formal_hidden_audit_credit = false
```

任何 reference-visible 决策都不能追认为 blind success。

---

## 1. 文献方法与本轮采用的简化原则

### 1.1 文献中的常见自动 hp 路线

本轮采用以下已有方法的共同思想，而不是继续发明 action-level 精确预测器。

1. Demkowicz 的 Maxwell 自动 hp 方法：
   - 从当前 coarse space 构造更丰富的 fine/reference space；
   - 求 fine solution；
   - 比较不同 h/p 候选对 fine solution 的 projection/interpolation error；
   - 按“误差下降 / 新增 DoF”选择 refinement。
   - DOI: `10.1016/j.cma.2004.05.023`。

2. Rachowicz–Pardo–Demkowicz 的 3D 自动 hp 方法：
   - 使用 coarse/fine two-grid；
   - fine solution 作为当前 cycle 的 reference solution；
   - coarse 与 fine 网格同时迭代，直到 coarse-fine error 达到容差。
   - DOI: `10.1016/j.cma.2005.08.022`。

3. Šolín–Demkowicz 的 goal-oriented hp 方法：
   - dual/DWR 用于判断哪些区域与目标量有关；
   - projection-based hp optimization 用于决定具体 h/p refinement；
   - 不要求一个 cellwise DWR 数值精确等于某个局部 action 的 endpoint delta。
   - DOI: `10.1016/j.cma.2003.09.015`。

4. 多层 hp 的 residual + smoothness 方法：
   - residual/error indicator 决定“哪里需要处理”；
   - 高阶系数或相邻 p-level surplus 的衰减决定“用 h 还是 p”；
   - 光滑、谱系数快速衰减区域优先 p；衰减慢或界面/奇异区域优先 h。
   - DOI: `10.1186/s40323-016-0085-5`。

### 1.2 本轮不再采用的过强要求

本轮禁止继续要求：

```text
cellwise DWR contribution
≈
actual selected-action endpoint delta
```

它已被 single-cell 与 four-cell actual candidate 否定。

本轮采用：

```text
where：DWR / residual / projection surplus 负责排序
how：p-surplus 衰减与 full p/h shadow 的实际效果决定 p 或 h
accept：candidate 的真实 PDE 与 reference-visible error 决定
```

---

## 2. “先找准、再压缩”的两阶段策略

### 2.1 本轮只做收敛主线

本轮不同时追求：

- 最少 DoF；
- 最少 rows；
- 最优局部 action；
- 最终 blind certificate。

本轮先找到一条稳定向 reference 收敛的 h/p 路径。

### 2.2 后续再做压缩

只有当某个 h/p 序列已经满足响应稳定、且与 reference 接近后，才开展：

```text
从已收敛空间向下 coarsen / p-down
```

不得继续从一个明显欠分辨的 coarse current 同时猜“怎样收敛”和“怎样最省内存”。

---

## 3. 固定 59-goal 指标

沿用当前正式 inventory：

```text
16 powers
32 co-amplitude real/imag components
5 totals
6 field goals
```

对每个目标 `J_j` 使用现有 reference-visible diagnostic 中已经冻结的 tolerance `tau_j`。

定义：

```text
E2(k)   = sqrt(mean(((J_k - J_ref)/tau)^2))
Einf(k) = max(abs((J_k - J_ref)/tau))

D2(k)   = sqrt(mean(((J_k - J_(k-1))/tau)^2))
Dinf(k) = max(abs((J_k - J_(k-1))/tau))
```

其中：

- `E` 只用于 development evaluator；
- `D` 是未来 blind controller 也能使用的内部稳定性量。

同时分别报告：

```text
power E2/Einf
amplitude E2/Einf
totals E2/Einf
fields E2/Einf
```

---

## 4. 八小时执行范围

### 4.1 硬限制

本轮最多运行：

```text
4 个新的 heavy MPI8 PDE
```

一次只运行一个。

禁止：

- 新建 package；
- 新建 campaign/state-machine 框架；
- 新增 schema/receipt/watchdog；
- exact selected-action Schur/low-rank 开发；
- p7 production；
- level-3 production；
- Path B；
- Hybrid；
- 迭代求解器；
- hidden-audit success 声明；
- 因 documentation/evidence 变化重跑 PDE。

允许的代码改动：

- 优先零代码，只复用现有 runner、plan 与 evaluator；
- 如必须增加辅助脚本，只允许一个 task-local 脚本，净新增不超过约 350 行；
- 不得修改 ordinary solver default；
- 单个 infrastructure blocker 若 45 分钟内无法解决，保存 blocker 并切换到下一项可执行实验，不得重构大框架。

### 4.2 M0：冻结已有结果，不运行 PDE

直接将既有 full p-shadow 登记为：

```text
development_cycle1_current_proposal
```

它已经完成正式 PDE，不得重新求解。

记录：

```text
current E2/Einf
full-p-shadow E2/Einf
full-h-shadow E2/Einf
```

确认 full p-shadow 的四类 normalized L2 均未系统性恶化后，development-only 提升为 cycle 1 current。

这只改变 development ledger，不改变 blind trial 历史。

### 4.3 M1：从 full p-shadow 构造下一层 p-enriched candidate

使用现有 p-shadow machinery，从 development cycle 1 current 构造一个新的 full p-enriched space。

原则：

- 不从 cellwise contribution 挑 1 个或 4 个 cell；
- 使用现有合法 p-shadow plan 生成器；
- production p 仍限于 `{4,5,6}`；
- inactive mode 不进入矩阵；
- exact sequence、Floquet、hanging、static condensation 保持现有 Gate；
- 不允许为了继续 p-up 临时开发 p7。

运行 1 个 MPI8 PDE，称为：

```text
P2 = development full-p candidate
```

P2 完成后立即做 reference-visible evaluator。

### 4.4 M2：根据 P2 结果决定第三个 PDE

#### 情况 A：P2 继续明显改善

若同时满足：

```text
E2(P2) <= 0.98 * E2(cycle1 current)
Einf(P2) <= 1.05 * Einf(cycle1 current)
totals E2 不恶化
residual/energy/resource Gate 通过
```

则优先再运行一个同类型 p-enriched candidate `P3`。

#### 情况 B：P2 基本停滞

若：

```text
E2 改善 < 2%
```

或 p-space 已因 `p<=6` 无法继续有效富集，则不开发 p7，改为从当前最优 p-space 运行一个现有 full h-shadow：

```text
Hcheck = one full-h candidate
```

h plan 必须复用现有 h-shadow discovery，不挑新的 action-level estimator。

#### 情况 C：P2 明显恶化

若：

```text
E2 增加 > 5%
```

或 totals/正式低阶输出系统性恶化，则拒绝 P2，保留 cycle1 current，并运行一个 `Hcheck`。

### 4.5 M3：可选第四个 PDE

只允许以下一种情况运行第四个 PDE：

```text
P lane 与 Hcheck 都分别改善，且二者改善的目标类别互补
```

此时可以运行一个 combined candidate。

否则第四个 PDE 不运行。

禁止为了“用满八小时”继续扫描参数或 cell。

---

## 5. h/p 决策依据

### 5.1 全局 lane 决策

根据实际 full shadow 结果，而不是 cellwise action prediction：

```text
p_gain = E2(current) - E2(full-p)
h_gain = E2(current) - E2(full-h)
```

规则：

```text
p_gain >= 5 * max(h_gain, 0)
    -> p-first

h_gain >= 2 * max(p_gain, 0)
    -> h-first

两者均 > 0，且比值在 [0.5, 2]
    -> 允许 combined check

两者均 <= 0
    -> 当前 shadow 设计失败，停止并报告
```

当前 cycle 0 已显示强 p-first 信号。

### 5.2 局部“哪里”

在需要构造 h plan 或解释 p plan 时，允许使用：

- multi-goal DWR magnitude；
- residual magnitude；
- p4/p5/p6 projection surplus；
- 材料界面与周期闭合规则。

这些指标只提供 ranking，不获得 endpoint-delta accuracy credit。

### 5.3 局部“h 还是 p”

优先复用现有 projection/surplus 工具，定义局部衰减比：

```text
rho_K = eta_(p->p+1,K) / max(eta_(p-1->p,K), eps)
```

建议初始分类：

```text
rho_K <= 0.35
    -> smooth / p-preferred

rho_K >= 0.60
    -> slow decay / h-preferred

0.35 < rho_K < 0.60
    -> keep or let global lane result decide
```

这只是工程初始阈值，必须在本轮报告中列出分布，不得为了匹配 reference 逐 cell 调参。

如果现有工具不能直接产生 `rho_K`，本轮不得为此重写 hierarchical basis；继续采用 full p/h lane 的真实结果。

---

## 6. 接受、停止与成功判定

### 6.1 Development candidate 接受条件

candidate 必须同时满足：

```text
E2_new < E2_current
Einf_new <= 1.05 * Einf_current
5 totals 不出现系统性恶化
full residual <= 1e-9
energy/Floquet/hanging/MPI pass
whole-job RSS <= 11 GiB
zero swap
```

accepted candidate 直接成为下一 development current，不重新求解同一 PDE。

### 6.2 内部响应稳定条件

未来 blind 可用的内部稳定信号为：

```text
D2 <= 0.5
Dinf <= 1.0
```

至少连续两个 accepted development steps 满足，才称为 response-stable。

如果 8 小时内未达到该条件，只报告收敛趋势，不继续扩展框架。

### 6.3 与收敛 reference 的最终比较

用户提出的理解基本正确：

```text
不断进行合法 h/p 富集
→ 正式响应变化逐步变小
→ 冻结候选
→ 与独立收敛 reference 比较
```

Development success 要求：

```text
59/59 within reference tolerance
```

若未全部通过，则按以下方式分类：

```text
STRONG_PROGRESS:
    E2 相对 cycle0 至少下降 50%，但未全部通过

PARTIAL_PROGRESS:
    E2 下降 10%–50%

STAGNATION:
    最优 E2 下降 <10%

DIVERGENCE:
    所有新候选均恶化
```

只有在 development 规则冻结后，才从初始网格重新进行一次真正 reference-blind validation；不得把本轮 reference-visible 路径改写为 blind success。

---

## 7. 资源与效率报告

每个新 PDE 只需记录：

```text
leaves
p4/p5/p6 counts
active FE DoF
condensed rows
matrix NNZ
factor NNZ
solver RSS
whole-job RSS/PSS/USS
swap
wall time
59-goal E2/Einf/D2/Dinf
category errors
accepted/rejected
```

不再新增多层 evidence wrapper。

报告必须区分：

- candidate solver structural memory；
- adaptive controller/postprocess total memory。

不得把生命周期释放冒充 h/p structural gain。

---

## 8. 八小时停止条件

任一条件满足立即停止并收口：

1. 已运行 4 个新 heavy PDE；
2. 已耗时约 8 小时；
3. 连续两个 candidate 恶化；
4. 连续两个 accepted step 达到 response-stable；
5. 出现 numerical Gate / OOM / swap；
6. 需要新增大于本任务允许范围的框架才能继续；
7. 同一 infrastructure blocker 超过 45 分钟未解决。

停止后只提交：

- 一个结果 Markdown；
- 一个 compact JSON/CSV；
- 必要的 plan files；
- 不超过一个小型 helper script。

不得继续自动开启 Path B、Hybrid、p7、level-3 或新的 task version。

---

## 9. 本轮最终要回答的问题

1. existing full p-shadow 是否可以直接成为 development cycle 1 current？
2. 第二层 p-enrichment 是否继续降低 59-goal true error？
3. p 收敛停滞后，h-refinement 是否开始产生明显收益？
4. successive response change 是否随 accepted cycle 下降？
5. 最佳 candidate 是否在 11 GiB 内？
6. 在不开发新大框架的前提下，能否得到一条可解释的 h/p 收敛序列？

本轮优先级：

```text
跑通收敛路径 > 找到最优局部 action > 完整 blind 认证 > 最小内存极限
```
