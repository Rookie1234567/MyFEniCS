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

## 2. 角色、分支与任务闭环

- ChatGPT 负责任务书、补充任务书和 `review_report_vN.md`。
- Codex 负责执行分支、实现、测试、正式运行、`outcomes/` 和 `response_vN.md`。
- **一个 Task 从创建执行分支到最终批准期间，ChatGPT 与 Codex 的全部任务材料都只能提交到同一个执行分支。**
- ChatGPT 不得在活动任务期间把 `task.md`、补充任务书、review、规则修订或其他任务过程材料直接提交到 `master`。
- Codex 不得为了取得 ChatGPT 的 review 而让 ChatGPT先写 `master`，也不得自行把未批准的执行分支合入 `master`。
- 若活动任务期间 `master` 出现无关更新，不得默认 merge/rebase 到执行分支；确有必要时先说明原因、影响和冲突风险，并取得用户或最新 review 的明确授权。
- Codex 不得删除、覆盖或弱化任务书、补充任务书、review 或本文件。
- 每轮实现结束后，Codex 提交并推送执行分支，给出精确完整 HEAD、base SHA、工作树状态、测试结果和证据索引，然后停止等待 ChatGPT review。
- ChatGPT 审阅时直接把新的 `review_report_vN.md` 提交到该执行分支；Codex从同一分支拉取后继续修改，不需要通过 `master` 中转。
- 只有 ChatGPT 最终审阅明确给出 merge approval，并且用户授权后，ChatGPT 才提醒 Codex将已批准的执行分支合并到 `master`。
- 最终合并由 Codex 执行；合并后必须报告精确 `master` SHA、合并方式、测试结果和工作树状态。除最终批准合并外，任何人不得直接在 `master` 开发。

## 3. Git 规则

- 从最新、干净的 `origin/master` 创建用户或任务书指定的执行分支；不得直接在 `master` 开发。
- 正式运行前后记录完整 SHA，并确认 tracked 修改和 nonignored untracked 文件均符合任务合同。
- 不整体 merge 或 cherry-pick 大型 research branch；只允许经过审查的最小文件级迁移。
- 每次提交只包含一个可说明的阶段或修复，不混入无关重构。
- 不 amend、强推或重写既有历史，除非用户明确授权。
- 负结果、受控停止和失败证据不得删除或改写为通过。

## 4. 目录与代码架构

### `src/`

存放可复用的项目主体：

- Maxwell/Floquet/DtN/QEP/Hybrid 数值内核；
- 网格、有限元空间、约束、求解器和后处理；
- 可被多个任务和 case 调用的通用实现。

任何改变物理方程、离散、矩阵、约束、求解或正式后处理的功能，都必须进入合适的 `src/` 模块并有测试。不得把新的数值算法只实现于 benchmark runner 中。

### `benchmarks/`

只用于：

- **通用且参数化**的 runner；
- watchdog、资源采样和 provenance；
- checker、聚合器和轻量证据生成；
- benchmark case 的配置、期望值和复现命令。

硬规则：

- 不应为每个单独的 p/h/M/MPI case 复制一个 Python 求解脚本；case 差异优先放在参数、JSON 配置或命令中。
- 新 runner 必须证明不能由现有通用 runner 加参数实现。
- task-numbered 脚本只允许作为薄的历史兼容入口或研究工具；不得继续累积数值核心和重复 orchestration。
- checker 不得重新实现求解器，只能读取原始记录并独立重算结论。
- 大型 mesh、field、matrix、factor、timeline 和原始输出必须进入 ignored artifact 目录，不进入 Git。

### `benchmarks/cases/`

每个 case 应优先包含：

- `README.md`；
- `config.json` / `schema.json` / `expected.json`；
- `test_command.txt`；
- 轻量、hash-bound 的 `records/`。

### `docs/`

任务书、review、outcomes 和技术文档默认使用中文；代码标识符、命令、状态枚举和必要术语保留英文。

## 5. 环境与 ABI

- 使用当前任务明确指定并已资格化的环境；不得从本文件假设 WSL、Docker、HPC 或固定本地路径。
- Python、MPI、PETSc/petsc4py、SLEPc/slepc4py、DOLFINx 和 Basix 必须来自同一 ABI 栈。
- 正式 Maxwell 计算必须确认 `PETSc.ScalarType` 为 `complex128`，并记录 `PETSc.IntType`。
- 每个 MPI rank 的解释器、库路径、scalar type 和线程设置必须一致。
- 环境或 ABI Gate 失败时，停止正式 PDE 并保存真实 blocker。

## 6. 数值可信度

- solver 成功只由 **full explicit true residual** 和任务规定的物理 Gate 判断。
- official R/T/A 只能由通过 residual Gate 的场产生。
- 必须区分 `measured`、`derived`、`predicted`、`not_run`、`failed` 和 `controlled_stop`。
- 未运行项不得写成通过；资源 Gate 停止不等于数值方法失败或该模型在其他软件中不可计算。
- 最细成功网格默认只能称为 best available discrete reference；没有独立证据不得宣称 continuum convergence。
- Full3D/Hybrid、direct/iterative、不同 MPI 数和不同环境之间的等价性必须由完整 observable vector 支持，不能只比较一个 R/T 数值。
- 数值核心发生变化时，必须明确哪些旧 evidence 失效，并重新运行对应 anchor。

## 7. 资源与重型运行

- 一次只运行一个 heavy case。
- direct 大算例按任务合同执行 preflight、assembly、factorization/setup、full solve 分级 Gate。
- 达到 termination 时终止完整进程组；OOM kill 不是合格停止。
- 内存必须说明口径：simultaneous process-tree/cgroup peak、单阶段峰值、历史峰值上界或累计对象体积不得混称。
- swap、pagefile 和 OOC scratch 分开记录。
- 资源预测必须说明假设、校准点、生命周期和不确定性；预测不得冒充实测或 solver pass。

## 8. 测试与证据

- 先运行最小相关测试，再运行任务书要求的回归、MPI、Ruff、compileall 和文档合同测试。
- 测试必须在最终改动后重跑。
- checker 必须从原始字段重算状态，不能只相信记录中的 `status`。
- 没有 GitHub Actions 时，只能陈述本地测试，不得声称 CI 通过。
- 正式记录必须绑定完整源码 SHA、环境、命令、MPI/线程、残差、official-result identity、资源口径、artifact hash 和正/负分类。

## 9. 汇总与可审阅性

`outcomes/summary.md` 必须表格优先，并至少包含：

- 任务范围、完成项、未运行项和负结果；
- 所有正式模型的统一结果表；
- p/h、Full3D/Hybrid、M 和 MPI 对结果及资源的影响；
- R/T/A、`A_volume`、重要衍射级、DoF/rows/NNZ、峰值内存和分阶段耗时；
- 数据身份、单位、baseline 和 evidence path；
- selective merge 分组和下一步。

同一物理量必须定义清楚。例如三维零级反射应优先分别报告 `R00_s`、`R00_p` 和两者之和 `R00_total`，避免含糊的 `R(0,0)`。

## 10. Selective merge

最终 manifest 必须按依赖组而不是只按文件罗列：

- production numerical/core；
- reusable runner/watchdog；
- checker/benchmark；
- compact evidence/docs；
- research-only；
- do-not-merge。

每项应说明数值行为是否改变、依赖文件、对应测试、fresh PDE evidence 和建议合入顺序。研究负结果可以保留为文档证据，但不得把未资格化研究路径提升为 production default。