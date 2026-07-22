# Task035 执行规则：Windows Codex 客户端、WSL 后端、连续自主研究

本文件只作用于 Task035，并在本目录内优先于根 `AGENTS.md` 的通用执行建议。

用户继续使用 **Windows Codex 客户端本身**与 Codex 对话和下达任务；不要求用户改用 Linux Codex CLI、VS Code、浏览器或其他前端。项目命令仍在 WSL Ubuntu 中执行。

## 1. 执行架构

```text
Windows Codex 客户端
→ 客户端 WSL 执行能力或显式 wsl.exe
→ WSL Ubuntu /home/Projects/MyFEniCS
→ Linux Git/Python/MPI/PETSc/SLEPc/DOLFINx
```

Windows Codex 客户端本身是 Windows 程序，不构成环境混用，也不得因此停止任务。真正禁止的是用 Windows Python、Windows Git、Windows MPI、Windows 仓库副本或 `/mnt/c`、`/mnt/d` 上的仓库执行本项目。

每个环境敏感命令必须在同一个 WSL shell 中完成：

```powershell
wsl.exe -d Ubuntu -- bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && <command>'
```

若已经位于 WSL shell，则使用：

```bash
bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && <command>'
```

禁止：

- `.venv/bin/python -m pytest`；
- 未 activation 的裸 `pytest`；
- `/usr/bin/python3` 直接运行项目；
- Windows `python.exe`、`git.exe`、`mpiexec.exe`；
- 依赖上一次 shell 的 `source`、`cd` 或环境变量；
- 给正常需要数分钟的测试或 PDE 设置任意短 timeout。

新的 shell/session 首次运行时做一次轻量 ABI preflight。只要 source SHA、activation 脚本和 ABI 未改变，不重复完整环境资格化。

## 2. 密码、密钥与人工交互

Codex 不得静默等待密码。执行可能交互的命令前先探测：

```bash
sudo -n true
ssh-add -l
env GIT_TERMINAL_PROMPT=0 git ls-remote origin HEAD
```

探针失败时，只暂停该操作并给用户可复制命令：

```bash
sudo -v
```

这里输入 WSL Ubuntu 用户密码；或：

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

这里输入 SSH 私钥 passphrase。不得在对话中要求用户粘贴密码、passphrase、token 或 API key。

若任务不需要系统包，不运行 `sudo`；若不需要网络或 push，不主动触发认证。

## 3. 连续自主研究模式

Task035 不再采用：

```text
完成一个或两个 Phase
→ 停止
→ 等待 ChatGPT 审阅
```

新的默认模式是：

```text
持续实现和试验
→ measured positive 则加深该路线
→ measured negative 则保存证据并切换路线
→ 直到形成可信 adaptive solution 或排除所有合理路线
```

`task.md` 的 Phase A–K 只用于组织范围和证据，不是审批锁。Codex 可以根据 measured evidence 调整顺序、跨 Phase 迭代和返回前一步修正，不需要逐阶段请求授权。

当前最新 `review_report_v4.md` 授权剩余 Task035 研究持续执行，包括：

- actual R1/R5/DWR/recovery/equilibrated estimator；
- tetra、hexa、hp 或其他可审查 backend；
- p2/p3/p4 Full3D adaptive cycles；
- Hybrid、M/DtN split；
- robust angle/common mesh；
- heavy cases，只要内部证据和资源 preflight 支持。

## 4. 候选管理

同时保持最多：

```text
2 条主候选 lane
+ 1 条 control/audit lane
```

避免无边界的参数和方法组合爆炸。

当前优先顺序为：

1. actual global two-level R5 + periodic tetra refinement；
2. actual cell/face R1 或 actual DWR + periodic tetra refinement；
3. cost-matched uniform tetra control。

若出现正信号，可以继续：

- local patch R5；
- recovery R3；
- equilibrated R4；
- global-p/local-hp；
- p3/p4 heavy；
- Hybrid adaptive；
- alternative hexa/octree/prism/pyramid/nonmatching backend。

若路线无正信号，记录 controlled negative 并切换，不等待审阅。

## 5. 正负信号规则

正信号包括：

- indicator 与独立 error proxy 稳定相关；
- estimator-marked refinement 后 observable 实际改善；
- 至少两个连续 cycle 正向；
- 相近成本下优于 uniform refinement；
- p2 结果可迁移到 p3/p4；
- Full3D 结果可迁移到 Hybrid；
- 网格质量、周期闭合、residual、physics、MPI 同时通过。

负信号包括：

- refinement 后目标误差不降或连续反弹；
- backend 无法满足周期闭合、质量或局部性；
- 收益被 factor fill、transfer 或 imbalance 抵消；
- 只能通过放宽 residual/physics Gate 得到“成功”；
- 合理修正后仍无可复现正信号。

单个 lane 失败只关闭该 lane，不停止整个 Task035。

## 6. Heavy run 与资源规则

Codex 可以自行推进到 p4/h5、Hybrid 和后续 heavy cases，不需要阶段审批，但必须：

- one-heavy-case-at-a-time；
- 运行前检查 rows/NNZ/memory/swap/disk/OOC；
- 使用 watchdog 和完整进程组终止；
- 先运行最低成本可区分实验；
- 正式 record 绑定 clean committed source SHA；
- OOM、swap thrashing、磁盘不足或进程异常时保留证据并调整方案；
- 不把资源终止写成数值成功或方法失败；
- 不进行无证据的大规模参数遍历。

## 7. 测试节奏

```text
小改动：targeted unit/fixture test
一个 lane 收口：serial + MPI2，必要时 MPI4
数值核心变化：相关 anchor/regression
重大里程碑或最终交付：full repository pytest
```

不再要求每个 Phase 或每几个提交运行 full pytest。README、schema、record、lint、链接或 metadata 问题只做 targeted rerun。

Phase A 已接受。只要绑定输入不变，不得重复：

- 环境安装或完整资格化；
- MPI1/2/4/8、MUMPS/PEP microfixture；
- Task034 六份 artifact 全量哈希；
- Task034 p3/h3、p4/h5、M funnel 或 MPI heavy runs。

## 8. 持续提交与报告

在以下时机提交并推送，但提交后继续工作：

- 一个候选实现可运行；
- 一个 measured experiment 完成；
- 一个 lane 得到 positive/controlled-negative 决定；
- 一个 heavy record 完成；
- 一个重大 bug 修复完成。

提交和 push 不是等待点。

持续更新现有文件：

```text
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/summary.md
docs/task035_hcurl_goal_oriented_adaptivity/outcomes/test_summary.md
benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records/
```

不要为普通进展创建新的 addendum、平行 review 或大量状态文档。

只有以下情况创建下一份 `response_vN.md`：

1. 已形成研究级或工程级 adaptive success；
2. 所有合理路线均被排除，需要架构决策；
3. 出现需要用户处理的硬 blocker；
4. 用户明确要求总结；
5. 准备最终 merge。

创建 response 后也不自动停止，除非属于第 2、3、5 类。

## 9. 真正停止条件

只有以下情况停止整个 Task035：

- 需要用户输入密码、SSH passphrase、凭据或系统级人工操作；
- WSL complex ABI、source/base hash 或 evidence identity 无法解释地不一致；
- accepted production core 或历史 evidence 被污染；
- MPI、true residual、official physics、periodic topology 或 mesh orientation 出现系统性错误，继续会制造虚假结论；
- 内存、swap、磁盘、OOC 或进程状态存在安全风险；
- 所有合理 estimator/backend/hp/Hybrid 路线均形成可审计负结果；
- 准备改变 ordinary default；
- 准备 merge `master` 或结束 Task035。

以下情况不得停止整个任务：

- 单个 estimator、fixture、backend 或 heavy case 失败；
- 一个明确且可局部修复的 bug；
- 某个 Phase pass 或 controlled negative；
- 文档、schema、record、lint 或链接问题；
- 需要换方法、参数、后端或求解策略。

## 10. 最终边界

Codex以解决自适应问题为目标持续探索，但不得伪造确定性成功。若最终没有路线满足可信成功标准，也必须给出完整的负结果地图和下一架构建议。

以下事项仍需要最终 ChatGPT review 和用户确认：

```text
将 research capability 宣称为 production default
改变 ordinary user-facing default
把 Task035 分支合并到 master
删除或改写 controlled-negative/failed evidence
```