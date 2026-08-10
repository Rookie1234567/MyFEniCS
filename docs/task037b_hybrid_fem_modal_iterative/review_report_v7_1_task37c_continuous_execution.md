# Task037b Review V7.1：Task37c 任务书随选择性合入并连续执行

## 0. 更正范围

本文件只更正 `review_report_v7.md` 中关于 Task37c 任务书与分支创建后停止的规定。
冲突之处以 V7.1 为准；Task37b 选择性合入白名单、full pytest、M10 integration anchor、
正常推送 `origin/master`、禁止 whole-branch merge和禁止 force push等要求仍全部由 V7约束。

```text
Task37c task.md prepared on Task37b branch = true
Task37c task.md selective merge to master  = authorized and required
Task37c branch creation                     = authorized after master push
Task37c remote branch push                  = authorized after master push
Task37c immediate execution                 = authorized after branch identity Gate
Task37c task rewrite after branch creation  = forbidden unless a later review requests it
Task37c work on Task37b branch or master    = forbidden
```

已准备的任务书为：

```text
docs/task037c_hybrid_iterative_robustness/task.md
```

该文件必须作为 Task37b 选择性合入的一项 docs-only交接内容进入更新后的 `master`。
不得把整个 Task37b docs历史为了带入该文件而整体merge；只移植该任务书及 V7最终允许的
Task37b结项文档。

---

# 1. Task37b selective merge 的新增要求

Codex 当前执行 Task37b selective integration时，必须把以下文件纳入拟推送的 master：

```text
docs/task037c_hybrid_iterative_robustness/task.md
```

同时可将本V7.1作为Task37b handoff文档选择性合入：

```text
docs/task037b_hybrid_fem_modal_iterative/review_report_v7_1_task37c_continuous_execution.md
```

要求：

- 这两项必须形成职责清晰的 docs-only commit或并入最终Task37b closeout docs commit；
- 不得因此扩大 solver code白名单；
- M10 integration anchor仍必须在包含Task37c任务书的拟推送HEAD上完成；
- Task37c任务书本身不得修改Task37b成功算法、ordinary defaults或master当前行为。

若无 deselect的full repository pytest在本V7.1提交到达前已经于拟集成代码HEAD上启动或完成，
不得中断、作废或仅因新增这两个docs-only文件而整套重跑。允许沿用该full pytest结果，前提是：

```text
full pytest code/config parent == final integration code/config
V7.1之后没有任何Python、配置、测试逻辑或ordinary-default改动
final HEAD重新运行documentation-contract tests
final HEAD重新运行Markdown rendering/checker、compile/diff checks
full pytest原始命令、parent SHA、结果和docs-only后继关系被准确记录
```

若full pytest本身出现failure，仍按V7停止；docs-only后继不能掩盖失败。
若V7.1到达后又发生任何代码或测试逻辑变更，则必须在新HEAD上重新运行full pytest。

若Task37b merge/test/M10 Gate失败，不得为了不中断而提前创建或执行Task37c。

---

# 2. Master推送后的连续交接

Task37b全部Gate通过并成功推送后，必须确认：

```text
local master SHA  == origin/master SHA
master worktree   == clean
Task37c task file == present on origin/master
```

随后从该 `origin/master` 精确创建并推送：

```text
codex/20260810-task37c-hybrid-iterative-robustness
```

要求：

```text
local Task37c SHA  == origin/master SHA at creation
remote Task37c SHA == local Task37c SHA
upstream           == origin/codex/20260810-task37c-hybrid-iterative-robustness
ahead/behind       == 0/0
worktree           == clean
```

若同名本地或远程分支已存在，禁止删除、强制移动或force push；必须验证其SHA是否与最新
`origin/master`一致。若不一致，停止并报告，不得在旧基线上执行任务。

---

# 3. 分支建立后无需再次等待任务书

与V7原规定不同，Task37c分支身份Gate通过后，Codex不需要再次停止等待任务书，因为任务书
已经由本轮提前写好并进入master。

Codex必须立即读取并执行：

```text
docs/task037c_hybrid_iterative_robustness/task.md
```

执行边界：

- 先完成Task37c R0 inherited-master audit和angle/polarization contract；
- 之后严格按任务书R1→R7顺序执行；
- 正式PDE只使用MPI8和MPI1；
- 只考虑S偏振、1°掠射、phi=-5/0/+5；
- 不扩展Task036失败案例、P偏振、更多角度、M200、0.7nm或新PC；
- 所有Task37c提交只进入Task37c分支，未经后续审阅不得merge master。

Task37c第一项提交必须是任务书规定的docs-only inherited audit，不得在新分支初始SHA上直接
启动重型PDE。

---

# 4. 连续执行中的最终报告边界

Task37b选择性合入和Task37c启动可在同一个Codex工作流中连续完成，但报告必须清楚分开：

```text
A. Task37b selective integration / tests / M10 master anchor / master push
B. Task37c branch creation / remote push / branch identity
C. Task37c R0-R7 execution and results
```

不得把Task37c结果写入Task37b response，也不得把Task37b历史负结果复制为Task37c新结果。

若Task37c执行时间较长，Codex可以在Task37c分支按任务书阶段提交并推送，不必回到Task37b
分支；但必须在任务书规定的Gate停止，不得自行扩大范围。

---

# 5. 最终优先级

```text
V7 Task37b selective integration and safety Gates = unchanged
V7 prohibition on prewritten Task37c task.md       = superseded by V7.1
V7 stop immediately after Task37c branch push      = superseded by V7.1
Task37c task.md scope and execution order           = binding after branch creation
```
