# Task43：工作站接入与 Codex 指令

## 1. 应接入哪个项目

推荐将当前 **task42extra-NN-V2 对应的 Codex 项目**改名/改任务为 Task43。旧任务记录的工作站目录是 `/home/fenics/Projects/NN-Lab-V2`，这只是已记录路径，执行前须检查它是否仍是对应 canonical clone 或注册 worktree。

项目显示名可以改为 `Task43 · 自适应 h/p 网格`。文件夹名称不必同步改名；先保持路径稳定。旧 NN-V2 的 FTT family 已正式关闭，更适合腾出工作槽位。另一个 NN-Lab 已经转为 phase-FE 研究，仍可保存其有效数值模块和历史证据。

本任务分支和初始文档已经在远端建立；**不要再次从 master 或旧 NN 当前 HEAD 建一个 Task43**。执行前读取远端 Task43 HEAD、父提交、文档，确认来自 `task40para@405e3aff42ac421a4c99315df1ed9b96941ecbe4`，并核对同名/近似名。

## 2. Codex 可直接接收的完整指令

```text
把这个项目切换为 Task43：自适应 h/p 网格研究。

仓库：Rookie1234567/MyFEniCS
唯一执行分支：task43_hp_adaptivity
已发布的初始代码基线：405e3aff42ac421a4c99315df1ed9b96941ecbe4
任务入口：docs/task43_hp_adaptivity/README.md
完整合同：docs/task43_hp_adaptivity/task.md

先核实当前工作站项目路径、git remote、worktree 注册、活动进程、工作树和 ignored
artifact。优先复用原 NN-Lab-V2 项目；保留旧分支、未提交成果和旧 artifact。
若有活动进程，不切换它正在使用的目录；若本地有改动，先识别归属并安全保全，
不得 reset --hard、clean、强推、无差别 stash，也不得覆盖其他活动工作区。

从 origin fetch 已存在的 task43_hp_adaptivity，在合适的已注册工作区建立或核对
对应 tracking branch，验证远端 HEAD、upstream、ahead/behind 与初始祖先。
已有正确本地分支只允许无冲突 fast-forward；分叉时先查明原因，不强制覆盖。
不要另从 master、Task41 或 NN 分支创建近似名字，也不要整体合并研究分支。

完整阅读根 AGENTS.md、docs/AGENTS.md、本任务 AGENTS.md、task.md、
baseline_audit.md 和任务书指定的旧 review/response。然后给出简短执行计划并开始。
已有明确授权，不要为了每个普通 bug、路径/格式错误、最小资格化修复反复停下询问。

第一阶段是新 phi90、50x50 周期、17x20 光栅的 13.5 nm 模型：
复用旧 local h / mixed p / hanging / Floquet 数值核心；p3 是新增资格化，
p4–6 可作明确标记的桥接。先以小规模 direct 核验真实 h/p 候选，目标3次、
至少2次 accepted updates，并完成独立更丰富离散和同精度成本比较。
投影指标只挑候选；实际 PDE 解和完整输出决定是否接受。

自适应空间的迭代接线独立验真；前置通过后才做一个0.7nm缩比pilot。
本轮不要自动启动全尺寸0.7nm campaign，不重启NN/FTT，也不盲扫PC参数。
使用现有已资格化complex128工作站环境，按任务书排队进行heavy case。

代码、测试、轻量证据和response均提交同一Task43分支，不改master。
最终提交outcomes/summary.md、response_v1.md、模型总账和选择性合并清单，
说明哪些是实际通过、部分完成、负结果、资源停止或未运行。
```

## 3. 获取分支的命令语义

在已经确认正确且可安全切换的项目中，首先执行非交互 remote 检查与 fetch：

```bash
git remote -v
git status --short --branch
git worktree list --porcelain
env GIT_TERMINAL_PROMPT=0 git ls-remote --heads origin task43_hp_adaptivity
git fetch origin refs/heads/task43_hp_adaptivity:refs/remotes/origin/task43_hp_adaptivity
```

以下创建命令**仅用于本地尚不存在该分支且工作区已确认可切换的情形**：

```bash
git switch --track -c task43_hp_adaptivity origin/task43_hp_adaptivity
git rev-parse HEAD
git rev-parse --abbrev-ref --symbolic-full-name '@{u}'
git rev-list --left-right --count HEAD...origin/task43_hp_adaptivity
git merge-base --is-ancestor 405e3aff42ac421a4c99315df1ed9b96941ecbe4 HEAD
```

若本地分支已存在，核对后切换该分支；只有落后且无分叉时使用 `git merge --ff-only origin/task43_hp_adaptivity`。如果目录仍被旧任务使用，先保全现有工作，并使用仓库已授权的 worktree 注册方式建立独立执行位置；不要用普通 clone 制造未登记副本。

本任务不要求通过 SSH 改动 `/home/fenics/Projects/laptop_share` 的主线工作区。也不要求把 NN-Lab-V2 重命名或删除；恢复旧研究只需要切回保留的旧分支及其原始 artifact。

## 4. 第一次状态回报应包含什么

| 项目 | 必须实测/读取的值 |
|---|---|
| 执行身份 | 机器、工作目录、git remote、branch、source HEAD、upstream、ahead/behind |
| 环境 | 实际解释器/activation、PETSc ScalarType/IntType、DOLFINx/Basix/MPI ABI |
| 现有能力 | p3 local、p4–6、local h level1/2、mixed trace、DtN、iterative 各自现状 |
| 最小实现 | 拟迁移函数、需要补齐的资格化和目标测试 |
| 首批运行 | current/shadow/h/p/独立参考/控制的有限 case 列表与资源预估 |
| 队列 | 当前 heavy 占用、Task43 可运行时段或继续开发的安排 |

这些字段是开始执行的事实核对，不是要求建立新的 orchestration 平台。没有运行的 PDE 必须明确写 `not_run`。
