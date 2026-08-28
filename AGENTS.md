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

### 2.1 双窗口主控—执行协作规则

- 仅当用户明确指定主任务与执行任务时启用本规则；否则不据此推断窗口角色。
- 主任务（Sol Max）只负责与用户沟通、阅读分析、任务合理性判断、任务拆解、执行监督，以及代码、结果和文档审核并决定下一步；不直接做项目开发或测试。
- 执行任务（Luna Max，标题“准备开发测试工作”）只接受主任务明确的小任务，按主任务书负责实现、测试、结果整理和必要文档。
- Luna Max 只做获批范围内的最小改动，不得擅自扩展目标、顺手重构、引入额外框架或进行过度防御。
- 执行任务开始前必须报告 branch、HEAD、upstream、dirty status、拟改文件、拟测项目和明确不做项，并等待主任务确认。
- 实现完成后、测试完成后和文档完成后，执行任务均须分别暂停，提交对应 diff、结果、证据和未解决项供主任务审核。
- 测试由执行任务负责；重型 PDE、长时 MPI 或资源密集运行必须有任务依据和主任务明确批准。
- 存在任务歧义、范围越界、环境风险或证据不足时，执行任务必须先停止并报告，不得自行猜测或补齐。
- 主任务审核通过后，执行任务才可按指令在同一工作分支 commit/push；随后报告完整 SHA、测试、证据和工作树状态，并等待用户与 ChatGPT 审核。
- 若本规则与用户本轮指令或任务权威文件冲突，立即停止受影响工作并报告，以较高优先级要求为准。

## 3. Git 规则

- 从最新、干净的 `origin/master` 创建用户或任务书指定的执行分支；不得直接在 `master` 开发。
- 正式运行前后记录完整 SHA，并确认 tracked 修改和 nonignored untracked 文件均符合任务合同。
- 不整体 merge 或 cherry-pick 大型 research branch；只允许经过审查的最小文件级迁移。
- 每次提交只包含一个可说明的阶段或修复，不混入无关重构。
- 不 amend、强推或重写既有历史，除非用户明确授权。
- 负结果、受控停止和失败证据不得删除或改写为通过。
- 会推送的任务执行目录必须是 canonical clone 登记的 worktree；不得把独立临时 clone 当作最终分支权威。若不得不用临时 clone，结项前必须在 canonical clone 中 fetch、建立或核对 local tracking ref，并验证 SHA、upstream 与 ahead/behind。
- 分支名必须与任务书逐字符一致；开始执行前应检查近似分支名冲突，避免把相似 ref 误当作当前任务的远端权威。

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

### 9.1 通俗解释原则

- `outcomes/summary.md`、`response_vN.md`、`review_report_vN.md` 和面向审阅的技术文档，不得默认读者已经理解有限元、电磁仿真、求解器或软件工程术语。
- 首次引入新的方法、算法、优化策略或数据指标时，除了给出专业名称，还必须先用通俗语言说明：它解决什么问题、为什么需要它、改变了计算流程中的哪一步、带来什么收益，以及付出什么代价。
- 不得只写 `static condensation`、`DWR`、`selective trace`、`preallocation`、`warm cache` 等名词后直接给结论；至少首次出现时说明其物理或数学含义和工程作用。
- 结果表格及其相邻说明必须让读者知道：模型是什么、使用什么方法得到、为什么比较它、指标代表什么，以及成功、失败或未完成的具体原因。
- 负结果不能只记录 `failed`、`controlled_negative` 或通过数，例如“10/12”；必须列出未通过的具体物理量、实际数值、参考或限值，并给出直观原因和证据入口。
- 文档目标是让没有参与具体开发过程的研究人员，也能仅凭文档理解研究对象、算法流程、关键决策、结果边界和下一步。

## 10. Selective merge

最终 manifest 必须按依赖组而不是只按文件罗列：

- production numerical/core；
- reusable runner/watchdog；
- checker/benchmark；
- compact evidence/docs；
- research-only；
- do-not-merge。

每项应说明数值行为是否改变、依赖文件、对应测试、fresh PDE evidence 和建议合入顺序。研究负结果可以保留为文档证据，但不得把未资格化研究路径提升为 production default。

## 11. 原生 Linux 执行环境

- 当前执行后端为原生 Ubuntu 24.04，项目执行目录为 `/home/fenics/Projects/MyFEniCS`；正式开发、测试、MPI/PDE 和重型 artifact 均必须在该原生 Linux 环境中执行。
- 禁止调用 WSL、`wsl.exe`、Windows Python、Windows Git、Windows MPI 或 Docker 代替当前执行环境；不得使用这些环境的仓库副本或工具链。
- `/media/fenics/Data` 只作备份来源，不得作为项目执行目录、正式测试目录或 MPI/PDE/artifact 目录。

## 12. 单一 Python 与原生 activation

- 当前主机的仓库级权威入口是 `source .venv/bin/activate_myfenics_native.sh`；需要项目 Python、MPI、PETSc 或 SLEPc 的命令必须在同一已激活 shell 中执行。
- activation 必须设置 marker `MYFENICS_NATIVE_COMPLEX_ENV=1`，并确保 Python、MPI、PETSc/petsc4py、SLEPc/slepc4py、DOLFINx 和 Basix 来自同一原生 Linux ABI 栈。
- 禁止直接使用 `.venv/bin/python -m pytest`、系统 `/usr/bin/python3` 或未 activation 的裸 `pytest` 替代资格化 activation；直接调用解释器不会自动设置 complex PETSc/SLEPc、`PYTHONPATH`、`LD_LIBRARY_PATH` 或项目 marker。
- 在任何耗时测试、MPI 或 PDE 前先运行轻量 ABI preflight，并确认：
  - `MYFENICS_NATIVE_COMPLEX_ENV=1`；
  - `sys.executable` 位于当前仓库 `.venv`；
  - `PETSc.ScalarType` 为 `numpy.complex128`，并记录 `PETSc.IntType`；
  - `petsc4py`、`slepc4py`、`dolfinx`、`mpi4py` 和 Basix 来自同一原生 Linux ABI 栈；
  - 实际执行路径中的 Python、MPI、Git 和数值库均为当前原生 Linux 版本。
- preflight 失败时，必须在启动 pytest、MPI 或 PDE 前立即停止；不得先运行测试，再用错误结果反推环境问题。

## 13. 密钥、密码与交互提示

- Codex 不得代替用户输入、记录、回显或推测任何 sudo 密码、SSH 私钥口令、GitHub 凭据、OpenAI/API 密钥或其他 secret。
- 非交互探针必须按实际认证路径选择；不得执行可能等待密码或确认的命令后静默卡住。
- Git 的权威探针是 `GIT_TERMINAL_PROMPT=0 git ls-remote origin HEAD`。该命令成功时，`ssh-add -l` 失败不是 blocker；当前仓库使用无口令的专用 `IdentityFile`，不应为此启动 `ssh-agent`。
- 包管理的权威路径是 `sudo -n /usr/local/sbin/codex-apt ...`，包安装只允许通过该免密包装器；普通 `sudo -n true` 失败属于预期的安全设计，不阻塞该包装器。
- 其他需要 root 权限的操作仍须遵守普通 sudo 边界：先使用非交互方式检查，若失败则停止并请用户在当前 Ubuntu 终端输入账户密码；Codex/ChatGPT 对话中不得粘贴任何口令。
- 若任务不需要安装系统包，不得主动运行 sudo；若不需要网络或 push，不得主动触发认证。

## 14. 防卡死、超时与测试金字塔

- 不得给正常需要数分钟的 full pytest、MPI、factorization 或 PDE 设置 5 秒、30 秒等任意短外层 timeout。timeout 只能用于任务书明确的资源 Gate，并必须记录预期时长和终止语义。
- 长命令启动前说明预计时长、输出位置和判定条件；能够输出 heartbeat、阶段日志或进程状态时应启用。
- 命令长时间无输出时，先区分：
  - 等待密码/确认提示；
  - 仍在消耗 CPU/内存的正常计算；
  - MPI 子进程存活但父进程等待；
  - 真正死锁或失联。
  在未检查进程树、CPU、日志和 prompt 前不得直接重复启动同一任务。
- 测试采用金字塔：
  1. 每个小改动只运行最小 pure-Python/单 fixture targeted tests；
  2. 每个组件阶段运行相关 serial/MPI2/MPI4 tests；
  3. 阶段收口运行 Task-focused suite；
  4. 只有在阶段 Gate 或最终交付前运行一次 full repository pytest。
- 已通过且由相同 source SHA、环境 ID、artifact hash 和 ABI 绑定的昂贵 Gate，不得因无关文档/元数据修改重复执行。只有相关输入变化时才重新资格化。
- 明确、局部、无歧义的文档、schema、scaffold、lint 或元数据错误，应先局部修复并 targeted rerun；不得自动触发环境重装、全量 artifact 校验或重型 PDE。

## 15. 文档收敛

- 当前任务的执行规则优先维护在任务目录的 `AGENTS.md`，审查要求优先维护在最新 `review_report_vN.md`。
- 用户或 ChatGPT 对尚未执行完的最新 review 作澄清时，应直接合并回该 review；不要为每次措辞修正创建新的 addendum、补充说明或平行权威文件。
- 临时补充文件的内容一旦并入主 review，应删除临时文件，避免 Codex同时读取多个相互覆盖的执行权威。
- 只有新增独立任务范围、需要保留不可变历史或主 review 已被后续 response正式回应时，才新建 addendum 或下一版 review。
