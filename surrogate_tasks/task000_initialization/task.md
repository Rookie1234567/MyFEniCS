# Task000 任务书：支线隔离、资源共存与前向数据接口初始化

## 0. 任务边界

本任务只初始化 `codex/only-one-13p5nm-surrogate-inversion` 支线，不开发正式代理网络，不执行参数反演，不改变现有有限元物理定义，也不接触 Task035d 工作树。

固定范围：

```text
repository_root = /home/Projects/MyFEniCS-Surrogate
execution_branch = codex/only-one-13p5nm-surrogate-inversion
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
initial_forward_source_sha = 9c2160d41382026352908d692ad479dc4508424d
wavelength = 13.5 nm
max_parallel_forward_solves = 1
heavy_lock = /home/Projects/.myfenics-heavy.lock
artifact_root = /home/Projects/_artifacts/surrogate
```

明确禁止：

- 修改 `/home/Projects/MyFEniCS` 中任何文件、Git 状态或运行环境；
- 切换、提交或推送 `master`、Task035d 或任何其他分支；
- merge/rebase/cherry-pick 其他分支；
- 为了方便而重构现有 FEM 核心；
- 同时启动两个前向 FEM；
- 运行正式大批量数据生成；
- 安装或升级共享系统 PETSc/SLEPc/MPI/DOLFINx/CUDA；
- 创建 PR 或合入 `master`。

## M0：双工作树只读审计

在任何修改前记录：

### M0.1 代理工作树

```bash
cd /home/Projects/MyFEniCS-Surrogate
git fetch --prune origin
pwd
git rev-parse --show-toplevel
git rev-parse --absolute-git-dir
git remote get-url origin
git branch --show-current
git rev-parse --abbrev-ref --symbolic-full-name '@{u}'
git rev-parse HEAD
git rev-list --left-right --count 'HEAD...@{u}'
git rev-list --left-right --count 'origin/master...HEAD'
git status --short
```

### M0.2 Task035d 工作树只读快照

只允许读取并记录，不得 fetch、checkout、pull、clean、reset、修改或运行：

```bash
git -C /home/Projects/MyFEniCS rev-parse HEAD
git -C /home/Projects/MyFEniCS branch --show-current
git -C /home/Projects/MyFEniCS status --short
```

将结果写入 Task000 outcomes。Task 结束时重复只读快照，并证明 Task035d 工作树未被本任务改变；若用户或另一个 Codex 会话在期间合法推进 Task035d，应明确区分外部变化，不得宣称由本任务造成或擅自回滚。

### M0 Gate

任一代理路径、分支、origin 或 upstream 不符，立即停止。不得自动修复到其他分支，先在 `response_v1.md` 报告。

## M1：安装本地 Git 防护

新增可审查脚本 `scripts/install_surrogate_git_guards.sh`，由 Codex 在当前代理克隆中执行。脚本必须幂等，并设置：

```text
push.default = simple
pull.ff = only
remote.origin.push = HEAD:refs/heads/codex/only-one-13p5nm-surrogate-inversion
```

建立 `.git/hooks/pre-commit` 与 `.git/hooks/pre-push`：

- 校验真实仓库根目录；
- 校验当前分支；
- 只允许代理远程 ref；
- 拒绝 branch deletion；
- 拒绝 non-fast-forward/force push；
- 拒绝从错误工作树提交；
- 输出清楚的 `BLOCKED:` 原因。

不得提交 `.git/hooks` 本身；只提交安装脚本和测试。不得使用 `--no-verify`。

### M1 负测试

不得真的修改远程错误分支。通过临时仓库、dry-run fixture 或直接调用 hook 输入，验证至少：

1. 正确分支提交允许；
2. 错误分支提交被拒绝；
3. 推送到 `master` 被拒绝；
4. 推送到 Task035d 被拒绝；
5. 分支删除被拒绝；
6. non-fast-forward 被拒绝；
7. 正确代理分支 fast-forward push 输入允许。

## M2：独立 activation、缓存和 artifact

新增 `scripts/activate_myfenics_surrogate_wsl.sh`。它应 source 仓库已有资格化 activation，而不是复制或替换 PETSc/DOLFINx ABI 逻辑，然后覆盖支线专属：

```bash
PROJECT_TAG=surrogate
TMPDIR=/tmp/myfenics-surrogate-${UID}
TMP=$TMPDIR
TEMP=$TMPDIR
XDG_CACHE_HOME=$TMPDIR/xdg-cache
MPLCONFIGDIR=$TMPDIR/matplotlib
MYFENICS_SURROGATE_ARTIFACT_ROOT=/home/Projects/_artifacts/surrogate
```

要求：

- `.venv` 必须位于当前代理仓库；
- 不得是指向 `/home/Projects/MyFEniCS/.venv` 的软链接；
- 创建独立 cache/artifact/run/log 目录；
- 默认线程限制保持可审计；
- 提供轻量 ABI preflight：Python 路径、complex PETSc、MPI/DOLFINx/Basix 来源、当前 root/branch；
- 失败时在 PDE 前停止。

更新 `.gitignore` 仅限必要的支线本地 artifact、dataset、checkpoint 和 run 目录模式；不得忽略源码或正式轻量 manifest。

## M3：共享 heavy lock 包装器

新增 `scripts/run_with_myfenics_heavy_lock.sh`，使用：

```text
/home/Projects/.myfenics-heavy.lock
```

要求：

- 非阻塞 `flock -n`；
- 获锁后只运行传入的单个 qualified command；
- 锁忙时返回独立、稳定的退出码，并输出 `controlled_stop = heavy_lock_busy`；
- 记录 run_id、PID/process group、开始/结束时间和退出状态；
- 不得等待锁释放后偷偷运行；
- 不得 kill 其他进程；
- 不得使用 `pkill`、`killall` 或 `wsl --shutdown`；
- 支持 signal trap，只清理自己创建的子进程组。

### M3 测试

使用轻量 `sleep` 或 dummy command 验证：

1. 第一个进程获得锁；
2. 第二个进程立刻 controlled stop；
3. 第一个结束后可再次获得锁；
4. 无遗留 lock holder 或错误全局清理。

## M4：工作区审计脚本

新增 `scripts/audit_surrogate_workspace.sh`，一次输出：

```text
repo root
git dir
origin
branch
upstream
HEAD
HEAD vs upstream
HEAD vs origin/master
worktree status
venv path
PETSc scalar/int type
TMPDIR/XDG_CACHE_HOME/artifact root
heavy-lock status (read-only probe)
```

审计脚本不得修改 Task035d，不得自动 clean/reset/pull/rebase。

## M5：前向数据薄封装与 schema

在不改变 FEM 内核的前提下建立最小 `src/forward_data/`：

### M5.1 参数 schema

定义版本化、可序列化参数对象，第一版只需覆盖已有 13.5 nm 模型能够真实接受的参数。禁止假装支持现有求解器尚未支持的参数。

参数应分层：

```text
physics
geometry
materials
illumination
discretization
solver
observables
execution
```

每个参数必须带：

- 名称与单位；
- 类型；
- 合法范围或枚举；
- 是否固定/可反演；
- 默认值来源；
- schema version。

### M5.2 `ForwardModel.evaluate`

建立薄适配器：

```python
ForwardResult evaluate(ForwardParameters, RunConfig)
```

本任务优先调用现有 runner/API，不复制求解器核心。适配器负责：

- 参数校验；
- 创建唯一 run directory；
- 调用单个 FEM；
- 收集结构化结果；
- 重新检查 residual/physics Gate；
- 写原始 record 和 compact manifest；
- 返回明确状态。

### M5.3 provenance

正式样本必须绑定：

```text
repository
branch
full source SHA
dirty state
parameter schema version
observable schema version
all config hashes
qualified environment identity
command
MPI/thread settings
start/end timestamps
peak process-tree memory
result status
artifact hashes
```

工作树 dirty 时，默认不得生成 formal training sample；只允许明确标记的 development smoke。

### M5.4 dataset manifest

定义轻量 manifest，但 Task000 不生成正式大规模 dataset。一个 dataset version 只允许一个完整 source SHA 和一个 observable schema。混源必须 fail closed。

## M6：单个 13.5 nm FEM smoke

仅在 M0–M5 全部通过后运行一次小型、已有且资源较低的 13.5 nm FEM smoke：

- 必须通过共享 heavy lock；
- `max_parallel_forward_solves = 1`；
- 不得选择 Task035d 的 p6/h10、MPI8/MUMPS 重型正式算例；
- 优先复用现有最小/低阶/粗网格受控 case；
- 运行前记录可用内存、Task035d 是否存在 heavy 进程和 lock 状态；
- 如果锁忙，受控停止，不等待、不干扰主线；
- 输出只能作为 development smoke，不得冒充训练集；
- 必须检查 full explicit true residual 和已有物理 Gate；
- 记录 process-tree peak RSS、wall time、CPU 使用、scratch 增长和 observable；
- 运行结束确认没有遗留 `python`/`mpiexec` 子进程。

如果现有 runner 无法被薄封装安全调用，应记录真实接口 blocker，不得为了通过 Task000 大改 FEM 核心。

## M7：收口、负证据和停止

生成：

```text
surrogate_tasks/task000_initialization/outcomes/summary.md
surrogate_tasks/task000_initialization/outcomes/test_summary.md
surrogate_tasks/task000_initialization/response_v1.md
```

`summary.md` 至少包含：

- 初始化范围；
- Git path/branch/upstream 防护结果；
- activation/ABI/cache/artifact 隔离；
- heavy lock acquired/busy 证据；
- 前向参数和 observable schema；
- smoke 结果或真实 blocker；
- Task035d 前后只读快照；
- changed paths；
- 未完成项与下一任务建议。

结束前：

1. 运行 targeted tests、必要 lint/compileall；
2. 再次审计 root/branch/upstream/status；
3. 只提交本任务文件；
4. 只推送到 `origin/codex/only-one-13p5nm-surrogate-inversion`；
5. 报告完整 HEAD 和 ahead/behind；
6. 停止，不开始正式数据生成、代理网络或反演。

## 验收重点

Task000 的核心不是“脚本存在”，而是以下风险已被 fail-closed 控制：

- Codex 走错工作树；
- 提交或推送到主线/Task035d；
- 两个 FEM 同时占用 WSL 资源；
- 两个项目共享 JIT/cache/tmp；
- 全局 kill 误伤另一个任务；
- 不同 FEM SHA 的数据混入同一训练集；
- 一个低质量 FEM 结果因程序正常退出而被误收为训练样本。
