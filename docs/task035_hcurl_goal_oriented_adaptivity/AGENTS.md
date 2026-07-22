# Task035 执行规则：Windows Codex 客户端，WSL 计算后端

本文件只作用于 Task035，并在本目录内优先于根 `AGENTS.md` 的通用执行建议。

用户将继续使用 **Windows Codex 客户端本身**与 Codex 对话和下达任务；不要求用户改用 Linux Codex CLI、VS Code、浏览器或其他前端。必须固定的是项目命令的执行后端，而不是对话界面。

## 1. 允许的工作方式

```text
Windows Codex 客户端
→ 通过客户端的 WSL 执行能力，或显式 wsl.exe 命令
→ WSL Ubuntu 中的 /home/Projects/MyFEniCS
→ Linux Git/Python/MPI/PETSc/SLEPc/DOLFINx
```

Windows Codex 客户端本身是 Windows 程序不构成环境混用，也不得因此停止任务。真正禁止的是用 Windows Python、Windows Git、Windows MPI、Windows 文件副本或 `/mnt/c`、`/mnt/d` 上的仓库执行本项目。

## 2. WSL 命令合同

每个依赖 DOLFINx、PETSc、SLEPc、MPI 或项目 Git 状态的命令，都必须在同一个 WSL shell 内完成：

```text
cd
+ activation
+ 必要的轻量 ABI preflight
+ 实际命令
```

Windows Codex 客户端可使用：

```powershell
wsl.exe -d Ubuntu -- bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && <command>'
```

若客户端已经提供原生 WSL shell，则使用等价的：

```bash
bash -lc 'cd /home/Projects/MyFEniCS && source scripts/activate_myfenics_wsl.sh && <command>'
```

禁止：

- `.venv/bin/python -m pytest`；
- 未 activation 的裸 `pytest`；
- `/usr/bin/python3` 直接运行项目测试；
- Windows `python.exe`、`git.exe` 或 `mpiexec.exe`；
- 依赖上一次 shell 中已经执行过的 `source` 或 `cd`；
- 给正常需要数分钟的测试或 PDE 设置 5 秒、30 秒等短 timeout。

新的 shell/session 首次执行环境敏感命令时做一次轻量 ABI preflight。只要 source SHA、activation 脚本和 ABI 未改变，同一阶段不重复完整环境资格化。

## 3. 密码、密钥与人工交互

Codex 不得静默等待密码。执行可能交互的命令前先探测：

```bash
sudo -n true
ssh-add -l
env GIT_TERMINAL_PROMPT=0 git ls-remote origin HEAD
```

探针失败时，停止该操作并给用户一段可直接复制到 WSL Ubuntu 终端的命令：

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

## 4. 测试节奏

- 小修改：只运行直接相关的 pure-Python 或单 fixture test；
- 一个真实 fixture 收口：serial + MPI2，必要时 MPI4；
- 一个 Phase 收口：Task035 focused suite；
- full repository pytest：每个审查批次最多一次，只在批次完成或最终交付前运行。

Phase A 已接受。只要 source SHA、环境、ABI、baseline descriptor 和 artifact hash 未改变，不得重复：

- 环境安装或完整资格化；
- MPI1/2/4/8、MUMPS/PEP microfixture；
- Task034 六份 artifact 全量哈希；
- Task034 p3/h3、p4/h5、M funnel 或 MPI 重型 PDE。

README、schema、record、lint 或 metadata 的局部问题直接修复并 targeted rerun，不得因此重新开始整个前置阶段。

## 5. 当前科学开发边界

Phase A 已通过。现有 NumPy 和小矩阵测试保留为：

```text
algebraic_precursor_pass
```

不得称为正式 H(curl) finite-element fixture qualification。

Phase B 的最低真实 FE Gate 为：

```text
B1 real periodic Nedelec/H(curl) fixture pass
+
B2 real flat-lossy-layer/official-goal fixture pass
+
serial/MPI2 identity
+
Task035 focused tests pass
```

达到后可进入 **Phase C-low-cost estimator bake-off**。

以下项目可与 Phase C-low-cost 并行：

```text
B3 material-interface/corner fixture
B4 Hybrid Et/Ht、M/DtN microfixture
R4 equilibrated estimator research lane
```

B3/B4 必须在正式完成 Phase D backend 决策或运行任何 p4/h5 adaptive heavy case 前完成，或者形成明确 controlled-negative 决定。

R2 暂时只记录：

```text
chi = |k|h/p
resolved / pre-asymptotic diagnostic
```

在没有可审查推导前，不得使用未经证明的缩放修改 R1 marking 权重。

## 6. 自动继续与真正停止条件

满足当前 review 的局部 Gate 后，Codex可在同一分支继续下一低成本步骤，不因明确、局部可修复的问题反复停下等待。

只有以下情况必须停止并报告：

- WSL complex ABI、source SHA 或 baseline hash 不一致；
- MPI identity、full true residual 或正式物理 Gate 发生系统性失败；
- 数学定义存在不明确且无法局部修复的问题；
- 需要启动尚未被 review 授权的目标 p4/h5 heavy case；
- 需要改变 ordinary default、任务范围或核心数值架构；
- 内存、swap、磁盘或进程终止 Gate 触发。

单个 estimator、fixture 或 mesh backend lane 失败时，应保留负结果并停止该 lane；只要其他主线仍满足当前 review 的最低 Gate，不得自动停止整个 Task035。

## 7. 文档规则

Task035 的执行规则只维护在本 `AGENTS.md`；当前审查要求只维护在最新 `review_report_vN.md`。不要为普通澄清继续创建新的 addendum 或平行说明文件。需要纠正时，由 ChatGPT直接更新当前 review，并删除已被合并吸收的临时补充文件。

## 8. 两阶段批次审查节奏

除非最新 review 另有规定，Task035 默认采用：

```text
连续完成两个相邻 Phase
→ 提交一个 response
→ 集中等待一次 ChatGPT review
```

在一个两阶段批次内：

- Phase 之间不因正常的 pass、controlled negative 或局部可修复错误停下来等待 review；
- 前一 Phase 的内部 Gate 通过后，自动进入下一 Phase；
- 某个方法 lane 失败只关闭该 lane，不阻塞其他候选；
- 每个 Phase 运行 focused tests，两个 Phase 完成后只运行一次 full repository pytest；
- 不得把“批次连续执行”解释为可以跳过 true residual、物理、MPI、网格质量、资源或证据 Gate。

当前批次由最新 Review V3 具体授权为：

```text
Phase C estimator bake-off
+
Phase D mesh-backend bake-off
```

完成 Phase D 后提交下一份 response 并停止等待集中审查。Phase E adaptive cycles、p4/h5 heavy mainline 和后续阶段不因本条自动获得授权。
