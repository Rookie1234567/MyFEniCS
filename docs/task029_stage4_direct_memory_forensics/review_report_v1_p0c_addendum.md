# REVIEW REPORT V1 补充：P0-C 长期 Task 回顾标准

## 1. 生效范围

本文件是以下审查报告的强制补充：

```text
docs/task029_stage4_direct_memory_forensics/review_report_v1.md
```

Codex 在提交 `response_v1.md` 时，必须同时回应主报告中的 P0-C 和本补充。

新增仓库级标准：

```text
docs/task_retrospective_standard.md
```

从 Task029 起，所有新 Task 都必须按照该标准维护任务目录内的详细结果总结和项目级 development progress。该要求不是只针对 Task029 的一次性文档修正。

---

# 2. P0-C 的修订定义

原 P0-C：

```text
重写 Task029 在 docs/development_progress.md 中的阶段记录。
```

现修订为：

```text
P0-C1：按统一框架重写 Task029 的 development progress；
P0-C2：把统一 Task 回顾框架固化为长期仓库规则；
P0-C3：为后续 Task 增加可执行的文档合同保护。
```

---

# 3. P0-C1：Task029 本轮详细回顾

Task029 在 `docs/development_progress.md` 中仍需按主报告要求，完整说明：

```text
1. 为什么启动；
2. 冻结物理模型和 baseline；
3. 使用的内存遥测和数值 Gate；
4. h5/h3 baseline；
5. KSPSetUp / MUMPS factorization 主峰；
6. H1–H7 调查方法；
7. release-base、MPI2、OOC、BLR、SuperLU_DIST、ordering 的结果表；
8. 哪些结果是实测、估算或外推；
9. h2 G1–G10 决策；
10. diagnostic_success / engineering_success=no；
11. 建议合并和拒绝提升的代码/profile；
12. 少 rank + 多线程的最终能力结论；
13. 后续转向 multilevel iterative 与 graded/adaptive mesh 的原因；
14. outcomes、Benchmark050、review/response 和关键代码链接。
```

不能用若干零散段落代替完整阶段结构。

---

# 4. P0-C2：固化为长期仓库规则

Codex 必须将：

```text
docs/task_retrospective_standard.md
```

加入项目总览，并明确其身份为：

```text
所有新 Task 完成后的强制阶段回顾标准
```

至少更新：

```text
docs/README.md
README.md（适合的位置，避免重复大段规则）
docs/repository_work_principles.md
```

## 4.1 工作原则补充

在 `docs/repository_work_principles.md` 的“结果与文档闭环”中增加长期条款，含义至少为：

```text
- 每个 Task 必须有结构化 outcomes/summary.md；
- 每个 Task 在最终审查前必须更新 docs/development_progress.md；
- development progress 必须包括背景、基线、方法、结果、解释、负结果、最终决策、局限、下一步和证据入口；
- 一句状态或纯文件链接不构成完整回顾；
- 详细 outcomes 与项目级 progress 职责不同，均不可省略。
```

根据现有治理规则，修改工作原则时必须同步：

```text
根 README 保护区
docs/README 保护区
src/test/test_24_repository_work_principles.py
```

用户已在本轮明确同意增加这一长期规则。

## 4.2 不要求立即重写全部历史 Task

本轮必须：

```text
- 完整补齐 Task029；
- 从 Task029 起对新 Task 强制执行；
```

本轮不要求：

```text
- 一次性重写 Task000–Task028 全部章节；
- 为旧任务重新运行数值计算；
- 删除旧的阶段索引或历史文档。
```

后续阶段收口任务可逐步补充旧 Task。

---

# 5. P0-C3：文档合同保护

Codex 必须增加或扩展 documentation contract，防止以后只写一句话。

最低自动检查：

```text
1. docs/task_retrospective_standard.md 存在；
2. docs/README.md 链接该标准；
3. repository_work_principles 包含 Task 回顾长期条款；
4. Task029 在 development_progress.md 中具有独立实质章节；
5. Task029 章节至少包含：为什么启动、方法、关键结果、结果解释、最终决策、下一步、证据入口；
6. Task029 章节链接 outcomes/summary.md、review_report_v1.md 和 Benchmark050；
7. Task029 章节明确 `diagnostic_success`、`engineering_success = no`、`h2 = not_run`；
8. 后续 Task 的任务模板或文档流程引用本标准。
```

测试不应只检查关键词随意出现在文件任意位置；至少应定位 Task029 章节后检查其内部内容。

---

# 6. 未来每个 Task 的执行闭环

从下一 Task 起，推荐固定顺序：

```text
task.md
-> implementation / experiments
-> outcomes/summary.md 按标准写详细档案
-> docs/development_progress.md 按标准写项目级回顾
-> review_report 检查代码、结果和回顾质量
-> response 修正
-> final review / merge decision
```

每个 Task 的 `outcomes/summary.md` 与 `development_progress.md` 都必须回答：

```text
为什么做
做了什么
怎么验证
得到了什么
为什么得到该结果
失败了什么
最终决定什么
下一步为什么
```

---

# 7. Response V1 新增回应要求

`response_v1.md` 必须新增：

```text
P0-C1 Task029 development progress rewrite
P0-C2 repository-wide retrospective standard adoption
P0-C3 documentation contract enforcement
```

每项写明：

```text
files changed
new rule or behavior
contract tests
Task029 section structure
remaining historical documentation gaps
```

不得把“已创建标准文件”视为全部完成；只有工作原则、索引、Task029 实际章节和测试同时更新，P0-C 才算关闭。
