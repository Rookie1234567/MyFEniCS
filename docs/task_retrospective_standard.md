# Task 阶段回顾与 Development Progress 写作标准

## 1. 目的

本标准用于保证每个 Task 完成后，用户能够在数周或数月后快速回答：

```text
为什么开始这个 Task？
基线问题和限制是什么？
具体采用了哪些方法？
进行了哪些实验和代码修改？
关键结果是什么？
哪些路线成功、失败或仅有正信号？
最终决定合并什么、拒绝什么？
下一步为什么这样安排？
```

禁止只在 `docs/development_progress.md` 中写一句“完成某功能”或“结果通过”。阶段记录必须包含足够的上下文、方法、数据、解释和决策。

本标准从 Task029 起适用于所有新 Task；后续整理旧 Task 时也应尽量按同一框架补齐，但不要求一次性重写全部历史任务。

---

# 2. 两层记录职责

每个 Task 完成时必须同时维护两层记录。

## 2.1 Task 目录内的详细执行记录

路径：

```text
docs/taskXXX_*/outcomes/summary.md
```

作用：

```text
- 保存该 Task 的完整执行事实；
- 记录所有主要实验、参数、失败路线和证据路径；
- 允许审查者复核数据与代码；
- 作为 review_report 的直接输入。
```

这是“详细技术档案”。

## 2.2 项目级阶段回顾

路径：

```text
docs/development_progress.md
```

作用：

```text
- 说明项目为何进入该 Task；
- 提炼方法、主要数字、解释和最终决策；
- 说明该 Task 如何改变项目能力边界；
- 指向详细 outcomes、Benchmark、review 和相关代码；
- 方便用户按时间线回顾整个项目。
```

这是“面向长期回顾的项目发展史”，不是 outcomes 的全文复制。

---

# 3. 每个 Task 的标准章节框架

`docs/development_progress.md` 中每个重要 Task 或紧密相关的一组小 Task，应至少包含以下内容。对于非常小的文档修正任务，可以合并精简，但不得遗漏最终决策和证据入口。

## 3.1 Task 身份与最终状态

必须先给出：

```text
Task ID / 名称
执行分支
基线 commit
最终 classification
review status
是否进入 master
是否改变 ordinary default
```

推荐格式：

```text
Task029 — Stage4 direct memory forensics
status = diagnostic_success
engineering_success = no
master decision = pending / merged / rejected
```

## 3.2 为什么启动

说明前一阶段留下的具体问题，避免只写抽象目标。

至少回答：

```text
- 哪个旧结果或瓶颈触发了任务？
- 为什么现有能力不够？
- 如果不做该任务，工程风险是什么？
- 本任务不解决哪些问题？
```

## 3.3 冻结问题、基线与比较口径

必须明确：

```text
- 物理模型；
- 几何、材料、边界、入射；
- 网格/阶次/DoF；
- solver/profile；
- reference record；
- 成功 Gate；
- 允许改变和禁止改变的量。
```

若与 COMSOL、论文或其他外部结果比较，必须列出可比性边界。

## 3.4 使用的方法

不能只列文件名，必须说明方法如何解决问题。

至少包括：

```text
- 理论或算法思路；
- 关键代码模块；
- 新增诊断或数据结构；
- 实验设计；
- 参数筛选顺序；
- 保护数值正确性的 Gate。
```

推荐用“方法—目的—证据”的表格。

## 3.5 实验矩阵或实施步骤

列出实际完成的主要运行或开发阶段，例如：

```text
baseline
candidate A
candidate B
negative screen
conditional large run / not-run decision
```

必须区分：

```text
planned
actually run
not run by Gate
failed
superseded
```

## 3.6 关键结果对比

至少放一张可独立理解的结果表。

表格根据任务类型选择指标，例如：

```text
数值任务：residual、R/T/A、field error、closure
性能任务：DoF、iterations、RSS、factor nnz、time
算法任务：equivalence error、rank、condition、convergence
文档任务：coverage、tests、remaining gaps
```

要求：

```text
- 明确 baseline；
- 明确正负号含义；
- 给出绝对值和百分比时说明分母；
- 不混用不同统计口径；
- 未运行项写 not_run，不留空或写 pass。
```

## 3.7 结果解释与根因

不能在结果表后直接结束。必须解释：

```text
- 为什么得到这些结果？
- 主导机制是什么？
- 哪些原假设被证实或否定？
- 哪些结论只是当前模型/环境内成立？
- 哪些量是实测，哪些是估算或外推？
```

## 3.8 成功路线、失败路线与负结果

分别记录：

```text
accepted / production candidate
engineering positive but unqualified
diagnostic-only
research-only positive
failed numeric Gate
failed performance Gate
not feasible with current framework
not run by safety Gate
```

失败路线必须保留准确原因，禁止只写“效果不好”。

## 3.9 最终决策与合并边界

必须明确写出：

```text
- 任务最终 classification；
- 哪些代码/文档/基础设施建议合并；
- 哪些 profile 不得提升；
- ordinary default 是否改变；
- 哪些 records 成为 canonical；
- 哪些研究代码留在分支；
- 是否允许进入 master。
```

推荐给出决策表：

| 对象 | 决定 | 原因 |
|---|---|---|
| telemetry | merge | 可复用、低风险 |
| candidate solver | reject | 未达到 Gate |

## 3.10 局限与尚未回答的问题

至少列出：

```text
- 当前结论的适用范围；
- 环境或数据缺失；
- 不能由本 Task 推出的结论；
- 后续若继续研究，需要先补什么证据。
```

## 3.11 下一步及其依据

下一步不能只列任务名称，必须说明因果关系：

```text
由于 A 已被证明不是主瓶颈，停止继续优化 A；
由于 B 显示正信号但未达 Gate，安排一个受控验证；
由于 C 是真正主导因素，下一任务转向 C。
```

## 3.12 证据入口

每个 Task 章节末尾至少链接：

```text
task.md
outcomes/summary.md
review_report_vN.md
response_vN.md（若有）
关键 Benchmark case / records
关键 theory / walkthrough
主要实现模块
```

---

# 4. `outcomes/summary.md` 强制模板

从 Task032 起，中型和大型算法、物理或性能任务的 summary 必须表格优先。叙述只解释表中根因、
边界和决策，不能替代状态、实验、数值、资源、负结果、合并与下一步表。每张表必须给出适用的
单位、baseline/分母、`measured` / `derived` / `predicted` / `not_run` 数据身份和证据入口。

Task032 及以后同规模 summary 至少应包含 8 张 Markdown 表，并使用下列结构：

```markdown
# TaskXXX 结果总结

## 1. 最终状态
## 2. 任务目标与非目标
## 3. 基线、冻结配置和环境
## 4. 实现与方法
## 5. 实验/运行矩阵
## 6. 关键结果表
## 7. 数值正确性与 Gate
## 8. 性能或资源结果
## 9. 根因解释
## 10. 成功路线
## 11. 失败、负结果与未运行项
## 12. 代码和文件变化
## 13. 最终合并建议
## 14. 局限
## 15. 下一步决定
## 16. 证据索引
```

不适用的章节必须在相应表中写 `not applicable` 或 `not_run` 并解释原因，不应直接删除导致读者
误解为遗漏。本规则不追溯要求一次性重写 Task000–Task031。

---

# 5. `development_progress.md` 推荐模板

```markdown
## TaskXXX：任务名称

### 最终状态

### 为什么启动

### 冻结问题与基线

### 采用的方法

### 主要实验/实施步骤

### 关键结果

### 结果解释

### 成功与失败路线

### 最终决策与合并边界

### 局限

### 下一步及原因

### 证据入口
```

对于多个连续的小任务，可写成一个阶段章节，但必须在章节中逐个说明各 Task 的作用和最终状态。

---

# 6. 写作质量要求

## 6.1 数据必须可追踪

重要数字应能追溯到：

```text
record JSON
CSV
run log
Benchmark README
review/response
```

不要只写没有来源的整数或百分比。

## 6.2 区分事实、解释和决策

推荐使用：

```text
实测结果：...
解释：...
决策：...
```

避免把推断写成实测事实。

## 6.3 保留负结果

失败和 not-run 是项目知识的一部分。不能因文档简化而删除：

```text
- 失败参数；
- 真残差不合格；
- 内存收益不足；
- 环境不支持；
- 安全 Gate 阻止运行；
- 被后续任务替代的旧结论。
```

## 6.4 控制重复

`outcomes/summary.md` 保存详细证据；`development_progress.md` 保存结构化提炼。可以复用关键表格，但不要机械复制全部日志和参数。

## 6.5 深度随任务规模调整

```text
大型算法/性能任务：完整使用全部章节；
中型功能任务：保留全部章节但可精简；
小型修正任务：至少写背景、修改、验证、决策、局限和证据。
```

---

# 7. 长期执行要求

从 Task029 起：

```text
1. Task 完成前，Codex 必须更新 outcomes/summary.md；
2. Task 进入最终审查前，Codex 必须更新 docs/development_progress.md；
3. review_report 必须检查该 Task 是否符合本标准；
4. response 必须说明更新了哪些阶段记录；
5. documentation contract 应检查新 Task 在 development_progress 中存在实质章节和证据链接；
6. 仅有一行状态或只有文件链接，不视为完成。
```

本标准本身不要求把所有历史 Task 立即重写。后续阶段收口任务可逐步补齐旧记录。
