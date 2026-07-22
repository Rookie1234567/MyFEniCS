# Task035 Review V2 补充：Windows 前端与 Phase B 快速解锁

本补充与 `review_report_v2.md` 共同构成当前执行权威。若两者在“必须使用 Linux Codex CLI”或“Phase B 全部 fixture 完成后才能进行任何 bake-off”方面存在冲突，以本补充为准。

## 1. 用户界面决定

用户明确希望继续在 Windows 图形界面中与 Codex 对话。该方式获得批准；**不要求用户安装、学习或日常使用 Linux 命令行版 Codex**。

推荐使用：

```text
Windows VS Code UI
+ WSL Remote workspace
+ Codex IDE extension/chat
```

用户从 WSL Ubuntu 终端执行一次：

```bash
cd /home/Projects/MyFEniCS
code .
```

然后在打开的 WSL VS Code 窗口中继续对话和开发。Windows UI 只作为前端；Git、Python、MPI、PETSc/SLEPc、DOLFINx 和测试仍在 WSL 中执行。

Codex 必须读取本目录 `AGENTS.md`，不得再以“用户没有运行 Linux Codex CLI”为 blocker，也不得要求用户为此重新建立环境。

## 2. 已接受且不得重复的前置工作

以下工作继续接受：

- Phase A WSL、complex ABI、MPI1/2/4/8、MUMPS/PEP；
- Task034 baseline 与 artifact binding；
- Case094 staging contract；
- algebraic precursor 和相关 unit tests；
- 正确 activation 下 full pytest pass。

除非 source SHA、activation、ABI 或 baseline identity 发生变化，不得重复上述工作。

## 3. Phase B 快速解锁修改

原 Review V2 对当前 algebraic precursor 的降级判断保持有效，但为避免前置阶段继续拖延，Phase C 拆成两个层级：

```text
Phase C-low-cost bake-off
Phase C-formal completion
```

### 3.1 Phase C-low-cost 解锁 Gate

只需完成：

1. 一个真实小型 DOLFINx/Nédélec periodic H(curl) fixture：
   - p1/p2；
   - actual mesh/UFL residual 或可审查 defect；
   - Floquet/orientation fault injection；
   - serial/MPI2 identity；
2. 一个真实 flat lossy layer 或等价低成本 FE fixture：
   - piecewise complex material；
   - 至少三个实际 h/p 点；
   - 实测 field/observable trend；
   - 一个 official R/T/A、R00 或明确 order functional 的 directional derivative/adjoint check；
3. Task035 focused tests、Ruff、compileall 和 diff-check 通过。

达到这些条件后，可以立即进入 Phase C-low-cost，对 R1、R3/R5、G1/G2 和 `kh/p` diagnostic 做低成本真实点筛选，不需等待新的 ChatGPT review，也不需运行 full repository pytest。

### 3.2 并行继续但不阻塞 low-cost Phase C

以下项目与 Phase C-low-cost 并行完成：

- material-interface/corner FE fixture；
- Hybrid Et/Ht、M/DtN split microfixture；
- R4 equilibrated research lane。

它们必须在：

```text
Phase D production mesh-backend selection
或任何 p4/h5 adaptive heavy run
```

之前通过或得到明确 controlled-negative 决定。

### 3.3 R2 边界

R2 暂时只记录：

```text
chi = |k|h/p
resolved / pre-asymptotic diagnostic
```

不得使用未经推导的 `1/sqrt(1+chi^2)` 改写 R1 marking 权重。

## 4. 测试节奏

- 每个实现小步：单测试；
- 每个真实 fixture 收口：serial + MPI2，必要时 MPI4；
- Phase C-low-cost 解锁：Task035 focused suite；
- material/Hybrid fixture 与 Phase C-formal 收口：一次 full pytest；
- 不得因文档、schema 或 record 修改重复 full pytest。

## 5. 当前授权

Codex拉取本补充和 Task035 `AGENTS.md` 后可直接继续真实 estimator/fixture 开发。Windows UI 不是 blocker。完成 B1+B2 最小 Gate 后可自动进入 Phase C-low-cost。

仍禁止：

- 直接运行真实 p4 adaptive；
- 把 algebraic precursor 称为正式 FE estimator qualification；
- 使用 Windows Python/Git/MPI 执行项目；
- 重复 Phase A 资格化；
- 为正常数分钟测试设置短 timeout。
