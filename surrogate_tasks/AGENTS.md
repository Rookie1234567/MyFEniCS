# Surrogate / Inversion 分支执行总则

本文件仅作用于 `surrogate_tasks/` 及其子目录，规定 13.5 nm 代理模型与参数反演支线的长期执行边界。Codex 在处理本目录中的任何任务前，必须先读取根目录 `AGENTS.md`，再读取本文件和当前任务目录中的 `README.md`、`task.md`、最新 review/response/outcomes。

## 1. 固定身份

```text
repository_root = /home/Projects/MyFEniCS-Surrogate
remote = https://github.com/Rookie1234567/MyFEniCS.git
execution_branch = codex/only-one-13p5nm-surrogate-inversion
initial_base_sha = 9c2160d41382026352908d692ad479dc4508424d
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
role = 13.5 nm forward-data generation + surrogate modelling + inversion
```

该支线与 Task035d 主开发相互独立。除用户在本轮明确授权的精确文件和精确 SHA 外，不得读取、修改、清理、提交、推送或执行 `/home/Projects/MyFEniCS` 工作树中的内容。

## 2. Git 硬边界

每次开始、提交、推送和正式运行前，必须确认：

```bash
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

必须满足：

```text
repo root = /home/Projects/MyFEniCS-Surrogate
branch = codex/only-one-13p5nm-surrogate-inversion
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
```

禁止：

- 在 `master`、Task035d 或任何其他分支开发、提交或推送；
- `git switch` / `git checkout` 到其他分支；
- 未经用户本轮明确授权，merge、rebase 或 cherry-pick `master`、Task035d 或其他研究分支；
- `git push --all`、`--mirror`、`--force`、`--force-with-lease`、`--no-verify`；
- 删除远程分支、修改或删除 `.git/hooks`、修改当前 branch/upstream/push 保护配置；
- 将本支线自行合入 `master`。

即使 `master` 或 Task035d 后续前进，本支线也不得自动同步。前向模型升级必须作为独立、可审查的迁移任务处理。

## 3. 主线最小侵入原则

本支线应尽量新增隔离模块，不直接重写 Task035d 正在发展的核心代码。推荐边界：

```text
src/surrogate/
src/inversion/
src/forward_data/
benchmarks/cases/1xx_13p5nm_surrogate_*/
docs/surrogate_*/
surrogate_tasks/
```

现有有限元程序在本支线中的主要角色是生成训练、验证和反演校准数据。优先通过薄封装调用稳定的前向求解入口，不在代理任务中顺便重构 local-h、variable-p、DtN、网格或求解器内核。

## 4. 前向模型封装合同

应建立统一、可测试的参数化入口，例如：

```python
result = forward_model.evaluate(parameters, run_config)
```

输入至少应支持：

- 波长，当前正式范围固定为 13.5 nm；
- 几何参数；
- 材料复折射率或等价介电参数；
- 入射角、方位角和偏振；
- 网格/阶次/求解器配置；
- 需要输出的 observable 集合；
- 运行身份、随机种子和 artifact 目录。

输出必须是结构化记录，至少包含：

```text
source_branch
source_sha
parameter_vector
parameter_schema_version
geometry_config_hash
material_config_hash
mesh_config_hash
solver_config_hash
observable_schema_version
R/T/A
selected diffraction channels
true residual and physics gates
DoF/rows/NNZ
runtime and peak-memory metadata
status = measured/derived/predicted/not_run/failed/controlled_stop
artifact paths and hashes
```

任何未通过 full explicit true residual 和任务规定物理 Gate 的结果，不得进入正式训练集。

## 5. 数据集不可混源

一个正式数据集版本只能绑定一个前向求解器完整 SHA 和一个 observable schema：

```text
dataset_v1 -> forward_solver_sha = 9c2160d...
dataset_v2 -> future approved forward solver SHA
```

禁止将不同源码 SHA、不同物理定义或不同 observable schema 的样本静默混入同一数据集。升级前向模型时，必须：

1. 冻结旧数据集；
2. 建立新数据集版本；
3. 在固定 anchor 参数点上比较新旧 R/T/A、衍射级、残差与成本；
4. 判断旧代理是否仍可使用，或是否必须重训。

## 6. 环境隔离

本支线必须拥有自己的 `.venv`，不得软链接或复用 `/home/Projects/MyFEniCS/.venv`。不得因代理任务修改共享系统 PETSc、SLEPc、MPI、DOLFINx、CUDA 驱动或系统 Python。

每个 WSL 命令必须在同一个 shell 中完成：

```text
cd -> branch/path gate -> source activation -> ABI preflight -> cache override -> actual command
```

在第一次 import DOLFINx/FFCx/Matplotlib 前，使用支线独立缓存：

```bash
export PROJECT_TAG=surrogate
export TMPDIR="/tmp/myfenics-${PROJECT_TAG}-${UID}"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export XDG_CACHE_HOME="${TMPDIR}/xdg-cache"
export MPLCONFIGDIR="${TMPDIR}/matplotlib"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$MPLCONFIGDIR"
```

大型 artifact 默认放入独立目录并纳入 `.gitignore`，例如：

```text
/home/Projects/_artifacts/surrogate/
```

## 7. 与 Task035d 的资源共存规则

两个工作树可以同时编辑、提交、推送和运行轻量测试，但共享同一个 WSL2 虚拟机、224 GB 内存预算、CPU、swap、SSD、`/tmp`、GPU 和系统 ABI。

默认规则：

- 同一时刻最多一个 heavy FEM/PDE；
- 支线前向样本生成默认 `max_parallel_forward_solves = 1`；
- 在获得单样本峰值内存、进程树峰值、scratch 和耗时证据前，不得提高并发；
- Task035d 正在执行正式 MPI/direct/MUMPS/PDE 时，本支线不得启动 FEM 样本生成；
- GPU 训练、轻量推理和不调用 FEM 的反演可以在限制 CPU 线程后与 Task035d 并行；
- 不得以“总内存看起来足够”为理由忽略 CPU、内存带宽、SSD/OOC、swap 和 MPI oversubscription。

双方 heavy FEM 必须竞争同一把非阻塞锁：

```text
/home/Projects/.myfenics-heavy.lock
```

示例：

```bash
flock -n /home/Projects/.myfenics-heavy.lock \
  bash -lc '<qualified single FEM command>'
```

锁不可获得时，应记录 `controlled_stop = heavy_lock_busy` 并停止，不得等待后偷偷并发，也不得修改 Task035d。

## 8. 进程安全

禁止使用可能误杀另一项目的全局命令：

```text
killall python
pkill -f python
killall mpiexec
pkill -f mpiexec
rm -rf /tmp/myfenics-*
wsl --shutdown
```

watchdog 只能终止自己创建并记录的 PID/process group。PID、日志和临时目录必须按项目与 run_id 隔离。

## 9. GPU 与 CPU 约束

代理训练应显式绑定 GPU，并限制 CPU 线程、DataLoader worker 和 BLAS 线程。不得因 GPU 训练在后台占满全部 CPU 或触发大量 page-locked memory，从而污染 Task035d 的资源评估。

每次正式训练应记录：

```text
CUDA_VISIBLE_DEVICES
GPU model and driver
framework version
CPU thread limits
DataLoader workers
peak GPU memory
peak host memory
training data identity
source SHA and seed
```

## 10. Task 闭环

每个 surrogate task 使用独立目录：

```text
surrogate_tasks/taskNNN_<name>/
    README.md
    task.md
    outcomes/summary.md
    outcomes/test_summary.md
    response_vN.md
```

Codex 每轮结束后只提交并推送本执行分支，报告：

- repository root、branch、upstream；
- base SHA 和完整 HEAD；
- ahead/behind upstream 与 master；
- changed paths；
- 工作树状态；
- 测试、数值 Gate、资源证据；
- 数据集和 artifact 身份；
- 未完成项、负结果和 controlled stop。

未经用户明确授权，不得开始下一 Task、合入 master 或升级前向求解器基线。
