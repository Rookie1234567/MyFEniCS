# MyFEniCS Codex 仓库总则

本文件作用于整个仓库，是长期稳定的**仓库级规则与导航入口**。它不得绑定任何当前 Task 编号、日期、执行分支、阶段顺序或临时环境路径。当前任务的范围只由用户本轮指令及对应任务目录中的 `README.md`、`task.md`、补充任务书和 review 文件确定。

优先级从高到低为：

1. 用户本轮明确指令；
2. 当前任务的 `task.md`、正式补充任务书和最新 `review_report_vN.md`；
3. 更深目录中的 `AGENTS.md`；
4. 本文件；
5. 其他说明性文档。

若这些来源冲突，停止受影响工作并在 `response_vN.md` 中报告；不得自行猜测或静默改写权威文件。

## 1. 每次开始前

1. 确认位于仓库根目录并读取本文件。
2. 阅读 `docs/repository_work_principles.md` 和 `docs/README.md`。
3. 从用户指令或当前执行分支识别任务目录，完整阅读其 `README.md`、`task.md`、全部补充任务书、最新 review、response 和 outcomes summary。
4. 阅读与本次改动直接相关的 architecture、theory、solver、benchmark 和 walkthrough 文档。
5. 检查 `HEAD`、`origin`、工作树、环境、ABI 和源码身份；未通过前不得正式运行 PDE。
6. **不得从本文件推断当前 Task。** 若用户指令、分支和任务目录不能唯一对应，先报告歧义。

## 新增：文档解释原则

- `summary.md`、`response_vN.md`、`review_report_vN.md` 和面向审阅的技术文档，不得默认读者已经理解有限元、电磁仿真、求解器或软件工程术语。
- 当引入新的方法、算法、优化策略或数据指标时，除了给出专业名称，还必须先用通俗语言解释“它解决什么问题、为什么需要它、改变了计算流程中的哪一步”。
- 不得只写例如“static condensation”“DWR”“selective trace”“preallocation”“warm cache”等名词后直接给结论；至少首次出现时需要说明其物理/数学含义和工程作用。
- 结果表格应同时说明：模型是什么、使用什么方法得到、为什么比较它、指标代表什么，以及成功/失败的原因。
- 负结果也必须解释失败的直观原因，不能只记录 `failed` 或 `controlled negative` 状态。
- 文档目标是让没有参与具体开发过程的研究人员也能根据文档理解研究路线、关键决策和结果边界。

## 2. 角色、分支与任务闭环

- ChatGPT 负责任务书、补充任务书和 `review_report_vN.md`。
- Codex 负责执行分支、实现、测试、正式运行、`outcomes/` 和 `response_vN.md`。
- **一个 Task 从创建执行分支到最终批准期间，ChatGPT 与 Codex 的全部任务材料都只能提交到同一个执行分支。**
