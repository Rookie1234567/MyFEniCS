# Task000 任务书：本地 Ubuntu 环境、前向封装与 p6/h10 可行性

## 0. 任务边界

本任务只初始化 `codex/only-one-13p5nm-surrogate-inversion` 支线在本地 16 GB Windows 笔记本上的执行环境，不开发正式代理网络，不执行参数反演，不进行批量训练数据生成，也不改变现有有限元物理定义。

固定范围：

```text
remote = https://github.com/Rookie1234567/MyFEniCS.git
execution_branch = codex/only-one-13p5nm-surrogate-inversion
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
initial_forward_source_sha = 9c2160d41382026352908d692ad479dc4508424d
platform = Windows + WSL2 Ubuntu
physical_memory = approximately 16 GB
wavelength = 13.5 nm
max_parallel_forward_solves = 1
```

本地 repository root、Ubuntu distribution name、Windows username、WSL username 和 artifact 路径必须由 Codex 实际探测，不得沿用工作站路径。

明确禁止：

- 在 `master`、Task035d 或其他分支开发、提交或推送；
- merge/rebase/cherry-pick 其他分支；
- 在 `/mnt/c`、`/mnt/d` 等 Windows 挂载目录执行正式 FEM；
- 未经用户明确确认就卸载 Docker Desktop、注销 WSL distribution、删除 Docker volume/image 或用户文件；
- 把卸载 `docker-desktop` 与删除用户新建 Ubuntu 混在同一命令中；
- 使用 Windows Python、Windows MPI 或混合 ABI 运行 FEM；
- 同时启动两个前向 FEM；
- 为了做成 `.exe` 而复制、删减或弱化求解器；
- 在 16 GB 机器上无预检反复强行运行 p6/h10；
- 创建 PR 或合入 `master`。

## M0：本地 Windows、WSL、Docker 与 Git 只读盘点

任何安装、卸载或代码修改前，先生成：

```text
surrogate_tasks/task000_initialization/outcomes/environment_inventory.md
```

至少记录：

### M0.1 Windows/WSL

- Windows 版本与 build；
- `wsl --version`；
- `wsl --status`；
- `wsl -l -v` 的全部 distributions、状态和 WSL 版本；
- 默认 distribution；
- 可用磁盘空间；
- 物理内存、pagefile；
- BIOS/虚拟化与 WSL2 前提是否满足。

### M0.2 Docker

只读盘点：

- Docker Desktop 是否安装、版本和安装位置；
- `docker-desktop` / `docker-desktop-data` 是否存在；
- images、containers、volumes 的数量和大致体积；
- 是否存在其他项目仍依赖 Docker；
- 哪些内容需要备份，哪些可删除；
- 卸载后预计释放空间。

不得在此阶段执行 `docker system prune`、删除 distribution 或卸载软件。

### M0.3 Git 工作区

用户完成本地 clone 后，自动解析真实 root，并记录：

```bash
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

必须满足唯一分支和 upstream。路径不得硬编码为工作站路径。

### M0 Gate

Codex 汇总拟执行的：

```text
保留内容
备份内容
卸载内容
新建内容
可能需要重启的步骤
```

然后停止，等待用户明确确认 Docker 卸载与 WSL distribution 变更范围。没有确认不得进入 destructive M1。

## M1：安全卸载 Docker Desktop 与旧 Docker WSL 组件

仅在用户明确确认后执行。

要求：

1. 对需要保留的 image/volume/project 给出可恢复备份或明确记录用户同意放弃；
2. 正常停止 Docker Desktop；
3. 通过 Windows 官方卸载入口或可审计命令卸载 Docker Desktop；
4. 仅删除经确认的 Docker 专用 WSL distributions；
5. 不得注销新 Ubuntu、其他用户 distribution 或含有用户项目的 distribution；
6. 卸载后重新运行 `wsl -l -v`、磁盘检查和 Docker 命令探针；
7. 把实际删除项、保留项和释放空间写入 inventory。

若 Codex 无法安全区分某个 distribution 或 volume 的归属，停止并要求用户人工确认，不得猜测。

## M2：安装或新建独立 WSL2 Ubuntu

目标是得到一个非 Docker 后端的、可长期复现的 Ubuntu distribution。

要求：

- 优先使用当前支持良好的 Ubuntu LTS；
- distribution 必须运行在 WSL2；
- 首次初始化由用户设置 Linux 用户名和密码，Codex 不得索取或回显密码；
- 启用 systemd 仅在环境确实需要并验证后执行；
- 更新基础包但不得无理由升级 Windows 或其他 distribution；
- 仓库 clone 到 Linux 文件系统，例如 `~/Projects/MyFEniCS-Surrogate`；
- 不在 `/mnt/c` 上建立正式 `.venv`、JIT cache 或 FEM artifact；
- 记录 Ubuntu release、kernel、filesystem、CPU、memory、swap 和 disk。

如果已经存在干净且合适的 Ubuntu，可在审计后复用，不得为了“新建”而无意义删除重装。

## M3：建立资格化 complex FEM 环境

### M3.1 安装策略

先完整阅读仓库已有环境说明、Dockerfile、Task034/工作站资格化脚本和依赖版本，再选择可复现方案。

优先级：

1. 与仓库当前已验证 ABI 尽可能一致的 Ubuntu 原生安装；
2. 项目本地 `.venv --system-site-packages` 加系统 complex PETSc/SLEPc/DOLFINx；
3. 必要时从源码构建项目本地 `dolfinx_mpc`；
4. 不再以 Docker 作为正式运行环境。

不得随意混用 apt、pip、conda 中来源不一致的 MPI/PETSc/DOLFINx。

### M3.2 安装脚本

新增可审查、幂等的：

```text
scripts/install_local_wsl_environment.sh
scripts/activate_myfenics_surrogate_wsl.sh
```

安装脚本必须：

- 分清需要用户 `sudo` 的系统步骤与普通用户步骤；
- 在可能提示密码前先说明；
- 不记录密码；
- 每一步失败即停止；
- 支持重复运行而不破坏已有成功环境；
- 把版本和来源写入 qualification 记录。

activation 必须设置：

```text
project-local .venv
complex PETSc/SLEPc
project-local dolfinx_mpc prefix
qualified PYTHONPATH/LD_LIBRARY_PATH/PATH
independent TMPDIR/XDG_CACHE_HOME/MPLCONFIGDIR
OMP/BLAS threads = 1 by default
```

### M3.3 ABI preflight

必须验证并记录：

- `sys.executable` 位于当前仓库 `.venv`；
- Python 版本；
- `PETSc.ScalarType == numpy.complex128`；
- `PETSc.IntType`；
- petsc4py/slepc4py/dolfinx/basix/ufl/ffcx/mpi4py/dolfinx_mpc 版本和真实路径；
- `mpiexec` 与 `mpi4py` 属于同一 MPI 栈；
- serial、MPI2 的轻量 import/hello 测试；
- FFCx JIT 可编译最小复数形式；
- 当前路径不含 Windows Python/MPI 污染。

输出：

```text
surrogate_tasks/task000_initialization/outcomes/environment_qualification.md
```

任何 ABI Gate 失败时不得进入 FEM。

## M4：Git 防护和本地工作区审计

建立幂等脚本：

```text
scripts/install_surrogate_git_guards.sh
scripts/audit_surrogate_workspace.sh
```

Git guards 至少设置：

```text
push.default = simple
pull.ff = only
remote.origin.push = HEAD:refs/heads/codex/only-one-13p5nm-surrogate-inversion
```

pre-commit/pre-push 必须拒绝错误分支、错误 remote ref、branch deletion、non-fast-forward/force push，并提供受控负测试。不得使用 `--no-verify`。

审计脚本输出 root、branch、upstream、HEAD、status、venv、ABI、cache、artifact、memory、swap 和 disk。

## M5：前向模型参数化薄封装

在不改变 FEM 数值核心的前提下建立：

```text
src/forward_data/
    __init__.py
    schema.py
    forward_model.py
    provenance.py
    cli.py
```

### M5.1 参数 schema

第一版只支持现有 13.5 nm 模型真实可接受的参数，按以下层次组织：

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

每个参数包含名称、单位、类型、范围/枚举、固定或可反演标记、默认值来源和 schema version。不得假装支持现有 solver 尚未实现的参数。

### M5.2 薄适配器

提供：

```python
ForwardResult evaluate(ForwardParameters, RunConfig)
```

职责仅限：

- 参数校验；
- 将参数映射到现有 runner/API；
- 创建唯一 run directory；
- 调用一个 FEM；
- 收集结构化结果；
- 独立检查 residual/physics Gate；
- 写 raw record、compact record 和 manifest；
- 返回明确状态。

不得复制 Maxwell、DtN、网格、组装、求解器和衍射后处理核心。

### M5.3 provenance 与 dataset contract

每个正式样本绑定：

```text
repository/branch/full source SHA/dirty state
parameter and observable schema versions
all config hashes
environment identity
command/MPI/thread settings
timestamps/process-tree peak memory
result status/artifact hashes
```

工作树 dirty 时不得生成 formal sample。一个 dataset version 只允许一个 source SHA 和一个 observable schema；混源 fail closed。

## M6：Linux CLI 与一条命令运行入口

实现可测试 CLI，例如：

```bash
python -m src.forward_data.cli run \
  --config path/to/sample.json \
  --output path/to/run_directory
```

CLI 必须：

- 先完成 root/branch/ABI/resource preflight；
- 解析并验证 JSON/YAML 参数；
- 只启动一个 FEM；
- 支持 dry-run；
- 返回稳定退出码；
- 在 stdout 输出紧凑摘要；
- 将完整证据写入 run directory；
- 失败后不遗留 MPI/Python 子进程。

先用 mock/dry-run 测试，再接真实低资源 FEM。

## M7：分级 FEM 验证与 p6/h10 受控尝试

### M7.1 轻量 smoke

依次运行：

1. import/JIT smoke；
2. pure-Python/配置 smoke；
3. 已有最小 serial 13.5 nm case；
4. 必要的 MPI2 小 case。

每一步记录 wall time、DoF/rows/NNZ、true residual、R/T/A 或现有 observable、process-tree peak RSS、swap delta 和 scratch。

### M7.2 p6/h10 preflight

在启动 p6/h10 前：

- 精确识别仓库中 p6/h10 的权威 case、命令、输入和 reference；
- 确认它与当前 source SHA 匹配；
- 根据已有工作站记录和本地小算例估算 assembly、factorization、peak memory 和 scratch；
- 设置阶段 Gate：preflight、mesh、assembly、factorization/setup、solve；
- 设定安全内存阈值、swap 阈值、scratch 阈值和受控终止语义；
- 不使用 OOM kill 作为合格停止；
- 不在用户正在使用电脑的重要时段无提示启动可能卡死系统的任务。

### M7.3 p6/h10 attempt

只有 preflight 认为存在合理成功可能时，才允许尝试一次。默认：

```text
max_parallel_forward_solves = 1
MPI ranks = evidence-based, not automatically all cores
BLAS/OpenMP threads = 1
```

结果分类：

- `passed`：完整 residual/physics Gate 和结果身份均通过；
- `controlled_stop`：资源 Gate 在 OOM 前安全停止；
- `blocked`：环境、接口、磁盘或已知内存预测表明不应启动；
- `failed`：真实数值或程序错误。

不得把“进程启动过”“swap 中跑完”“只得到部分输出”写成 passed。

输出：

```text
surrogate_tasks/task000_initialization/outcomes/p6h10_feasibility.md
```

若 p6/h10 不适合 16 GB，Task000 仍可成功完成；下一阶段应改用经验证的低资源离散生成初始数据，或另立任务研究迭代/静态凝聚/降阶数据生成，不得在本任务中扩展范围。

## M8：Windows `.exe` 封装可行性

目标不是强行制造单文件程序，而是给用户尽量简单的运行入口。

依次评估：

### 方案 A：Linux CLI

这是正式数值权威入口，必须先通过。

### 方案 B：Windows launcher `.exe`

推荐方案：小型 Windows launcher 接收配置路径和输出路径，随后调用：

```text
wsl.exe -d <qualified Ubuntu> -- bash -lc '<activate + Linux CLI>'
```

launcher 必须：

- 不嵌入密码；
- 正确处理 Windows/WSL 路径转换；
- 显示 Ubuntu/环境缺失错误；
- 传递退出码；
- 保存日志；
- 不隐藏 WSL、Ubuntu 和 Linux FEM 运行时依赖。

可先实现 PowerShell 或 Python prototype，再决定是否用 PyInstaller/.NET 打包 launcher。

### 方案 C：真正原生单文件 Windows FEM `.exe`

只做技术审计和最小实验。必须检查 PETSc、MPI、DOLFINx、dolfinx_mpc、FFCx JIT、动态库和数据文件依赖。若不可行，应明确写 `not_supported`，不得牺牲数值功能或复制 solver 伪造支持。

输出：

```text
surrogate_tasks/task000_initialization/outcomes/packaging_feasibility.md
```

Task000 的最低可接受交付是可靠 Linux CLI；Windows launcher 成功属于加分项；真正原生单文件 Windows FEM `.exe` 不是强制通过条件。

## M9：收口与停止

生成：

```text
surrogate_tasks/task000_initialization/outcomes/environment_inventory.md
surrogate_tasks/task000_initialization/outcomes/environment_qualification.md
surrogate_tasks/task000_initialization/outcomes/p6h10_feasibility.md
surrogate_tasks/task000_initialization/outcomes/packaging_feasibility.md
surrogate_tasks/task000_initialization/outcomes/summary.md
surrogate_tasks/task000_initialization/outcomes/test_summary.md
surrogate_tasks/task000_initialization/response_v1.md
```

`summary.md` 至少包含：

- Docker/WSL 初始状态、实际卸载和保留内容；
- 新 Ubuntu 身份和安装方式；
- environment/ABI qualification；
- Git guards；
- 前向 schema、CLI 和 provenance；
- smoke 结果；
- p6/h10 passed/controlled_stop/blocked/failed 及具体证据；
- `.exe` 三种方案结论；
- changed paths；
- 下一阶段数据生成的 go/no-go 条件。

结束前：

1. 运行 targeted tests、必要 lint/compileall；
2. 再次审计 root/branch/upstream/status；
3. 只提交本任务文件；
4. 只推送到 `origin/codex/only-one-13p5nm-surrogate-inversion`；
5. 报告完整 HEAD、ahead/behind、测试、环境和资源证据；
6. 停止，不开始批量数据生成、代理训练或反演。

## 验收重点

Task000 的核心不是“安装成功”或“做出 exe”这两个口号，而是：

- Docker 已按确认范围安全退出，不误删其他 WSL 数据；
- Ubuntu 原生 complex FEM 栈可复现且 ABI 一致；
- 16 GB 下不会通过无约束重算把电脑拖入 OOM/swap 失控；
- FEM 已被薄封装为可参数化、可审计、可生成训练样本的入口；
- p6/h10 的结论由实测或可信 preflight 支持；
- 用户最终能通过 Linux CLI，最好再通过 Windows launcher，简单地输入配置并获得结果；
- 本支线没有修改或干扰 Task035d 主开发。
