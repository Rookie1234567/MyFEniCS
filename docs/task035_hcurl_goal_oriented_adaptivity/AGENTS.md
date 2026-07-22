# Task035 执行规则：Windows 前端、WSL 后端

本文件仅作用于 Task035，并在本目录内优先于根 `AGENTS.md` 的通用执行建议。用户可以继续使用熟悉的 Windows 图形界面与 Codex 对话；**不要求用户改用 Linux 命令行版 Codex**。必须固定的是代码和命令的执行后端，而不是对话界面。

## 1. 推荐工作方式

首选方式是：

```text
Windows VS Code 图形界面
+ VS Code WSL workspace
+ Codex IDE extension/chat
+ WSL Ubuntu 内的 Git/Python/MPI/PETSc/DOLFINx
```

用户只需在 WSL Ubuntu 终端执行：

```bash
cd /home/Projects/MyFEniCS
code .
```

随后在新打开的 VS Code 窗口中继续像 Windows 软件一样使用 Codex。该窗口必须显示 WSL/Ubuntu remote identity；仓库路径必须是 `/home/Projects/MyFEniCS`，不得打开 Windows 下的重复副本。

Windows Codex app、Windows 浏览器或其他 Windows UI 可以用于对话、审阅和下达任务；若其工作区没有连接到 WSL，则不得直接用 Windows Python、Git、MPI 或 Windows 文件副本执行本项目。不要要求用户为了本任务学习或日常操作 Linux Codex CLI。

## 2. WSL 执行合同

- Git、Python、pytest、MPI、PETSc/SLEPc、DOLFINx 和 PDE 必须在 WSL Ubuntu 中运行。
- 每个环境敏感命令必须在同一个 shell 内完成仓库定位、activation 和执行：

```bash
bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && <command>'
```

- 禁止直接使用 `.venv/bin/python -m pytest`、系统 Python 或 Windows Python。
- 不要求每条小命令重复完整环境资格化。新的 shell/session 首次运行时做一次轻量 ABI preflight；只要 source SHA、activation 脚本和 ABI 未变化，同一阶段内复用该结果。
- 不得从 Windows 外层为正常 pytest、MPI 或 PDE 设置 5 秒、30 秒等任意短 timeout。

## 3. 用户人工准备与密码

只有发生认证或权限需求时才打断用户。Codex 先运行非交互探针，不得静默等待密码：

```bash
sudo -n true
ssh-add -l
env GIT_TERMINAL_PROMPT=0 git ls-remote origin HEAD
```

探针失败时，向用户说明只需在 WSL 终端运行哪一条命令：

```bash
sudo -v
```

这里输入 WSL Ubuntu 用户密码；或：

```bash
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

这里输入 SSH 私钥 passphrase。不得在对话中要求用户粘贴密码、passphrase、token 或 API key。

## 4. 防止重复无用测试

测试采用固定金字塔：

1. 小修改：只运行直接相关的 pure-Python 或单 fixture test；
2. 一个真实 fixture 收口：serial + MPI2，必要时 MPI4；
3. 一个 Phase 收口：Task035 focused suite；
4. full repository pytest：每个 Phase 最多一次，且只在解锁下一 Phase 或最终交付前运行。

已由相同 source SHA、环境、ABI、baseline descriptor 和 artifact hash 绑定的 Phase A Gate不得重复。文档、schema、README 或 compact metadata 的局部修复不得触发环境重装、MPI1/2/4/8 重资格化、artifact 全量哈希或 Task034 重型 PDE。

## 5. Task035 快速开发边界

Phase A 已接受；现有 NumPy/代数 fixture 保留为 `algebraic_precursor_pass`。为尽快进入真正算法开发，Phase B 不再要求四类正式 fixture 全部完成后才开始低成本 bake-off。

最小解锁条件为：

```text
B1 real periodic Nedelec/H(curl) fixture pass
+
B2 real flat-lossy-layer/official-goal fixture pass
+
serial/MPI2 identity
+
Task035 focused tests pass
```

达到上述条件后，可以立即进入 **Phase C-low-cost estimator bake-off**，同时并行继续：

```text
B3 material-interface/corner fixture
B4 Hybrid trace/M/DtN microfixture
R4 equilibrated estimator research lane
```

B3/B4 必须在选择正式 mesh backend、启动 Phase D 重型路线或运行任何 p4 adaptive 之前完成，但不得继续阻塞低成本 Phase C 开发。

R2 在有可审查推导之前只作为 `kh/p resolution diagnostic`，不得修改 R1 marking 权重。

## 6. 自动推进

满足当前 review/addendum 的局部 Gate 后，Codex可在同一分支自动继续下一低成本开发步骤，不必因明确、可局部修复的问题反复停止等待。以下情况才必须停止并请求用户或 review：

- WSL/complex ABI、source SHA 或 baseline hash 不一致；
- MPI identity、true residual 或正式物理 Gate 失败；
- 需要运行目标 p4 heavy case；
- 需要改变 ordinary default、任务范围或核心数学定义；
- 内存、swap、磁盘或进程终止 Gate 触发。
