# Task39extra Review V30：本机阶段最终收口与Task40extra交接

## 0. 主控决定

本机双凝聚研究阶段以 **PASS_WITH_QUALIFICATIONS / CLOSED_WITH_QUALIFICATIONS** 收口。最终推荐、公式、历史结果、时间/内存和继承边界集中于 [final_report.md](final_report.md)。它是后续任务首先阅读的技术入口。

本review授权的是：**旧任务只做离线证据/文档收口；随后从真实收口提交建立用户指定的新研究分支，按新task开展新的0.7nm小模型批次。** 不是继续在旧任务跑13.5nm优化，不重跑V29/V30/V31，不自动迁移工作站。

```text
repository                 = Rookie1234567/MyFEniCS
reviewed_branch            = task39extra
reviewed_base_HEAD         = e09bd1612c4f6ca5fb5cf3572835748ad5c16207
last_review_response       = review_report_v29.md / response_v33.md
old_task_response_required = response_v34.md
old_task_new_PDE_limit     = 0
next_branch                = task40extra_0p7nm_engineering
next_task_directory        = docs/task40extra_0p7nm_engineering
next_branch_base            = actual verified Task39extra closeout commit
ordinary_default_change    = NOT_APPROVED
master_merge               = NOT_APPROVED
workstation_changes        = NOT_AUTHORIZED
```

## 1. 最终技术选择

速度优先推荐：p6/p4装配时单元凝聚，p6 trace/port right FGMRES，准确p4凝聚MUMPS，BAL_H与现有快速A6/A4、blocked Gram、reference-metric对角、H6自然序、低扰动RSS监控。MUMPS、p4阶次、真实A4检查不因本次收口改变。

V31补跑126步，原A6最终及释放后约9.2832e-7，功率/体吸收闭合通过；worker workflow2313.526s、树RSS7,331,401,728B。保留V29完整性能口径2422.426s及既有完整场对照，不将不同边界拼成因果加速结论。p3约4.03GB/361步/117.77分钟是旧实现备选，不写成最新公共内核的实测。

保留所有未采用候选和首场Codex误停记录。8GiB旧容量试验和历史RSS成绩不得重新成为停止authority。

## 2. C0–C2：只用已有文件收口

| 阶段 | 必做工作 | 停止/继续规则 |
|---|---|---|
| C0 身份 | 核对canonical worktree、最新HEAD、upstream、无活跃旧本机worker；读适用AGENTS、工作原则、最新授权 | 有后续合法提交先审差异，不reset；不为写docs中断正在运行的任务 |
| C1 离线核验 | 对V31补跑与可得V29/V30数组做物理/mesh/keys绑定后比较；从旧预检补ABI/线程；提取已有时间边界 | 不新PDE、不重建factor；缺旧数组/字段写EVIDENCE_LIMITED；真实不一致先报告并阻断相应继承 |
| C2 收口提交 | 落库final_report与本review，写response_v34，追加summary入口、test_summary/run_index和项目级索引/总账；保留旧记录 | 有限离线缺口不阻止阶段收口，但不得写已通过；回读远端完整SHA |

同离散对照沿旧阈值：FE L2/scaled-curl、同坐标E/H和模式复幅值相对差<=1e-4，R/T/A/A_volume绝对差<=1e-5，逐模式功率差<=1e-6；近零量报告绝对误差，不拟合整体相位。只有原始文件可得才运行相应checker；不可得不是一次新重跑的理由。

不修改已运行input、run_manifest、旧summary或source SHA以补假证据；新增独立closeout记录。检查器和文档必要修复须标明工具source及raw hashes。对既有结果“复算范数”不冒充重新执行原A6算子。

## 3. 分支建立及文档顺序

由Codex创建分支，符合仓库角色划分。本轮用户明确指定从task39extra延伸，因此允许stacked研究分支，不需先合并master。

1. 在旧任务canonical worktree完成C2，提交并push `origin/task39extra`；回读remote HEAD。
2. 将真实SHA记为`CLOSEOUT_SHA`，确认本报告、review与新增证据都在其中。
3. 在canonical clone登记新的worktree/branch `task40extra_0p7nm_engineering`，base严格为该SHA。远端同名已存在时先核对归属与ancestry，不覆盖、不force；不同任务冲突则停止并报告。
4. 只在新分支落库配套`docs/task40extra_0p7nm_engineering/README.md`和`task.md`，生成`branch_provenance.json`，记录真实base、上游e09bd…、父final_report blob/hash、用户授权与本次交付manifest。
5. 新任务task首批授权生效后连续执行，不在“branch已建”或“只做了小组件”处反复停审。新结果/response只写新任务目录。

本文件不包含一个虚构的未来closeout SHA；真实值由上述提交动作绑定。若用户交付的是本地文件包，文件包本身不是远程commit。Codex必须按分支顺序提交，不能将新task先写在旧任务或master上。

## 4. 收口验收和不做的工作

旧任务新增PDE=0；不更换PC、不新增MUMPS参数扫描、不清理研究历史、不启用失败候选、不构建新的性能平台。原始数值记录、测试失败、误停和资源策略都保留。

必须检查新文档fenced math、表格和仓库链接，运行相关文档合同测试，并在实际提交后看GitHub rendered view。不可访问时写明未完成项，不能虚称已检查。

收口交付：final_report.md、本review、response_v34.md及必要轻量离线证据/索引。重型场、因子、日志留ignored artifacts。若新task启动，最终对话同时回报旧分支closeout SHA、新分支HEAD、branch-base关系及新任务response_v1路径。

**关闭本机研究阶段不等于批准merge master或宣布通用0.7nm生产能力。** 下一阶段要以真实0.7nm非可分小模型、误差和资源证据为起点，不再把当前全局p4因子视为不可改变的最终架构。
