# MyFEniCS Codex 执行总则

本文件作用于整个仓库。它是 Codex 的**导航与硬规则入口**，不是项目知识全文；详细事实、任务范围和数值 Gate 以 `docs/` 中的权威文件为准。进入更深目录时，如存在更深层的 `AGENTS.md`，则其局部规则优先；用户本轮明确指令和当前任务书优先于本文件。

## 1. 每次开始工作前必须做什么

1. 确认当前工作目录是仓库根目录，并读取本文件。
2. 读取 [`docs/repository_work_principles.md`](docs/repository_work_principles.md)。
3. 读取 [`docs/README.md`](docs/README.md)，确认当前任务和历史入口。
4. 读取当前任务目录的 `README.md`、`task.md`、全部任务补充书，以及上一任务的最终 `review_report`、`response` 和 `outcomes/summary.md`。
5. 读取与本次改动相关的 architecture、theory、walkthrough、benchmark 和 solver 文档；不要只依赖聊天摘要或文件名猜测。
6. 检查 Git、环境和源码身份，未通过前不得写代码或启动正式 PDE。

当前正式任务是 **Task034**。必须同时读取：

```text
docs/task034_workstation_wsl_adaptive_scalability/README.md
docs/task034_workstation_wsl_adaptive_scalability/task.md
docs/task034_workstation_wsl_adaptive_scalability/task_fixed_geometry_convergence_addendum.md
```

Task034 的执行分支必须是：

```text
codex/20260717-task34-workstation-wsl-adaptive-scalability
```

`agent/wsl-environment-qualification` 只是 WSL bootstrap 报告分支，不是 Task034 执行分支；其报告 `docs/workstation_wsl_environment_qualification.md` 只能作为前置参考，不能冒充完整 Phase A。

## 2. 角色和任务闭环

- ChatGPT 负责任务书、补充任务书、远程审查和 `review_report_vN.md`。
- Codex 负责创建执行分支、实现、测试、正式运行、`outcomes/` 和 `response_vN.md`。
- Codex 不得删除、覆盖或弱化 ChatGPT 编写的 `task.md`、任务补充书、`review_report*.md` 或本文件。
- 对任务书有异议、发现冲突或需要改变范围时，在 `response_vN.md` 中说明并停止受影响阶段；不得静默改写权威文件。
- 任务完成后必须推送执行分支，提交 `response_v1.md`，给出 HEAD、base SHA、测试和证据索引，然后停止等待 ChatGPT review。
- 未经最终 review，不得自行合并 `master`。

## 3. Git 与分支规则

开始 Task034 时必须从最新、干净的 `origin/master` 创建分支：

```bash
git fetch origin --prune
git switch master
git pull --ff-only origin master
git status --short --untracked-files=all
git rev-parse HEAD
git rev-parse origin/master
git switch -c codex/20260717-task34-workstation-wsl-adaptive-scalability
git push -u origin codex/20260717-task34-workstation-wsl-adaptive-scalability
```

硬规则：

- `HEAD` 必须等于 `origin/master`，工作树必须无 tracked 修改和 nonignored untracked 文件。
- 不得直接在 `master` 开发。
- 不得从大型 research branch 整体 merge 或整体 cherry-pick。
- Task033 中被排除的 adaptive、graded mesh、1 TiB 和 full-campaign prototype 不得直接提升；只能只读参考并在 Task034 从 clean base 重新实现。
- 每次提交只包含本阶段相关文件；不要混入无关重构。
- 不 amend、重写或强推已有历史，除非用户明确授权。
- 每次正式运行前后都检查 `git status --short --untracked-files=all` 和完整 SHA。
- 结束时保持工作树干净，并推送所有已提交工作。

## 4. WSL 原生环境规则

Task034 正式环境是 WSL2 Ubuntu，不以 Docker 作为通过依据。

```bash
cd /home/Projects/MyFEniCS
source .venv/bin/activate-myfenics
```

必须满足：

- 仓库位于 WSL Linux 文件系统 `/home/...`，不得从 `/mnt/c`、`/mnt/d` 等 Windows 挂载目录运行正式任务。
- 不得混用 Windows Python、Git、MPI、PowerShell、CMD 或 WindowsApps。
- Python、mpi4py/Open MPI、PETSc/petsc4py、SLEPc/slepc4py、DOLFINx 和 Basix 必须属于同一套 WSL ABI。
- `PETSc.ScalarType` 必须是 `numpy.complex128`；记录 `PETSc.IntType`。
- 每个 MPI rank 的 Python、库路径和 scalar type 必须一致。
- 当前 `.venv` 激活脚本是本机 bootstrap；Task034 必须补充可复现的环境探针或安装/激活入口，不得只依赖未跟踪文件。
- 裸 `/usr/bin/python3` 当前可能指向 real PETSc，不得用于 MyFEniCS 正式运行。
- 环境身份、版本、路径、MPI、MUMPS、SLEPc PEP 和 WSL 资源必须写入结构化 outcomes。

环境或 ABI Gate 失败时，停止所有正式 PDE，先修复环境并记录负结果。

## 5. 代码修改原则

- 先阅读现有实现、测试和历史结论，再修改代码。
- 优先最小、可审查、可回退的改动；避免顺手重构无关模块。
- ordinary solver default、默认网格、默认后处理和默认 profile 不得静默改变；新路径必须显式 opt-in。
- 不允许为了通过测试而放宽数值阈值、删除负结果、跳过检查或伪造记录。
- 如果 Maxwell、Floquet、QEP、Hybrid coupling、DtN、场重构或 official postprocess 数值 kernel 改变，必须明确标记旧 evidence 失效，并重新运行对应 PDE anchor。
- diagnostic、lifecycle、watchdog 和资源监控改动也必须有测试，不能因“不改数学”而省略验证。
- 当前 Task034 hardening 必须处理：Floquet cache 生命周期、active-column 全局 Python allgather、共享主机 swap 权威、完整 source-clean 语义和 evidence-to-current numerical blob checker。

## 6. 数值可信度硬规则

- solver 成功只由 **full explicit true residual** 判断；KSP 内部残差、预条件残差或 projected residual 不能替代。
- official R/T/A 只能从通过 residual Gate 的场产生。
- probe、sampled flux、中心线或单点值默认只作 diagnostic，除非任务书另有正式资格化。
- full3D/Hybrid、direct/iterative、MPI1/MPI8/MPI16、缓存 hit/miss 和不同环境结果必须有明确等价性证据。
- 每个正式结果都要区分 `measured`、`derived`、`predicted`、`not_run` 和 `failed`。
- 未运行项不得写成通过；资源受控停止不得写成数值方法失败。
- 负结果必须完整保留，包括失败 Gate、停止原因、资源边界和未允许的推论。
- 最细成功网格默认只能称为 best available discrete reference；没有独立证据时不得声称 continuum convergence。

## 7. Task034 的科学执行顺序

严格遵守：

```text
WSL environment qualification
-> post-merge hardening
-> Task033 anchor reproduction
-> p3/h3 staged reference
-> p4/h5 staged workstation study
-> fixed-geometry p2/p3/p4 convergence
-> full3D-Hybrid same-degree closure
-> MPI1/MPI8/MPI16 identity and scalability
-> Case093 canonical benchmark freeze
-> conforming graded-h
-> genuine fixed-p h-adaptivity
-> resource-model recalibration and 0.7 nm assessment
```

补充边界：

- p1 Hybrid 先做 capability audit；正式 Hybrid 收敛从 p2 开始。
- p2/p3/p4 固定结构收敛和 Case093 必须在 measured adaptive compression 前完成。
- 固定 `p`、由场相关 indicator 逐轮局部加密属于 genuine h-adaptivity；一次性手工 graded mesh 不是 adaptive。
- p4 每个候选必须经过 preflight、assembly-only、factorization-only、full solve 分级 Gate。
- MPI16 禁止 oversubscription；未资格化时必须写 `mpi16_not_qualified`，不得静默替换。
- Task034 不运行 0.7 nm 正式 PDE，不实现 arbitrary variable-p H(curl)，不运行 p4/h3 或更细候选，除非新的 ChatGPT review 明确解锁。

## 8. 资源和重型运行规则

- 一次只允许一个 heavy case。
- 大 direct 运行必须按 `preflight -> assembly-only -> KSPSetUp/factorization-only -> full solve` 推进。
- 每次运行前刷新可用内存、进程树、job/cgroup swap、磁盘、scratch 和 source identity。
- 达到任务书 termination threshold 时终止完整进程组；OOM kill 不属于合格停止方式。
- formal no-swap 以当前 job/process tree 和专用 cgroup 为权威；WSL/host 全局 `pswpin/pswpout` 只作 diagnostic。
- Linux swap、Windows pagefile 和 MUMPS OOC scratch 必须分开记录。
- OOC 只作为显式 profile，scratch 必须位于本地 Linux 高速文件系统并在结束后清理。
- 不得并发启动多个重型案例，也不得假设更多 MPI rank 必然更快或更省内存。

## 9. 测试与验收

每次改动后先运行最小相关测试，再运行任务书要求的完整组。至少包括：

```text
focused pure-Python tests
DOLFINx native WSL tests
MPI2 / MPI4 component regression
MPI1 / MPI8 / MPI16 formal matrix where required
Task032 anchors
Task033 anchors
Task034 tests
Ruff
compileall
git diff --check
git status --short --untracked-files=all
```

规则：

- 测试必须在最终改动后重新运行。
- 缺少依赖、环境或资源时，记录真实 blocker，不得虚构通过。
- checker 必须从原始字段重新计算结论，不能只相信 JSON 的 `status`。
- 文档改动也必须运行文档合同测试，并检查 GitHub rendered view。
- 没有 GitHub Actions 运行时，不得说“CI 已通过”；只能陈述本地测试证据。

## 10. 文档语言与格式

- 项目任务书、outcomes、review 回应、技术总结、benchmark 说明和项目进展默认使用中文。
- 代码标识符、命令、API 名、文件名、状态枚举和必要英文术语保留英文；首次出现时用中文解释。
- 不提交只有一句状态或只有文件链接的总结。
- `outcomes/summary.md` 必须表格优先，并包含范围、实验矩阵、关键数值、资源、失败/not-run、合并决定和下一步。
- 每张数值表标明单位、baseline、数据身份和 evidence path。
- 独立公式使用空行包围的 `$$` block；不要把需要渲染的公式放入代码围栏。
- 表格列数必须一致，单元格中的竖线要转义，不把多行公式塞进表格。
- 重要 Markdown 推送后必须检查 GitHub rendered view。
- 详细写作标准见：
  - [`docs/task_retrospective_standard.md`](docs/task_retrospective_standard.md)
  - [`docs/markdown_rendering_standard.md`](docs/markdown_rendering_standard.md)

## 11. Evidence 与文件存放

Git 中只提交轻量、可复查内容：

```text
JSON / CSV summaries
Markdown outcomes
配置与 schema
compact residual history
source/environment identity
artifact hash descriptors
tests and checkers
```

重型内容必须留在 ignored 路径：

```text
results/
benchmarks/artifacts/
benchmarks/artifacts/cases/<case>/
```

不得提交 mesh、VTU/XDMF/HDF5、完整场数组、矩阵、因子、OOC scratch、原始 PEP cache、完整 memory timeline 或大型日志。

## 12. 任务结束前检查

结束前必须确认：

1. 任务范围内代码、测试和文档均已完成或明确 fail closed。
2. 所有正式 positive 均通过 true residual 和对应物理 Gate。
3. 所有失败、not-run 和受控资源 negative 均被保留。
4. `outcomes/summary.md`、`outcomes/test_summary.md`、`outcomes/changed_files.md`、`docs/development_progress.md` 和 `response_v1.md` 已更新。
5. 需要合并的文件有逐文件 `selective_merge_manifest.csv`；失败研究代码默认留在任务分支。
6. 工作树干净，分支已推送。
7. 不自行合并 master，停止并等待 ChatGPT review。
