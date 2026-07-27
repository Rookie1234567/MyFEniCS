# Surrogate / Inversion 分支执行总则

本文件仅作用于 `surrogate_tasks/` 及其子目录，规定 13.5 nm 代理模型与参数反演支线的长期执行边界。Codex 在处理本目录中的任何任务前，必须先读取根目录 `AGENTS.md`，再读取本文件和当前任务目录中的 `README.md`、`task.md`、最新 review/response/outcomes。

## 1. 固定身份

```text
remote = https://github.com/Rookie1234567/MyFEniCS.git
execution_branch = codex/only-one-13p5nm-surrogate-inversion
initial_base_sha = 9c2160d41382026352908d692ad479dc4508424d
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
role = local 13.5 nm forward-data generation + workstation GPU surrogate/inversion
```

当前支线采用两阶段硬件分工：

```text
本地 16 GB Windows 笔记本 + WSL2 Ubuntu：
    环境安装、前向封装、单样本 FEM、训练数据生成

工作站：
    拉取已经生成的数据集，执行 GPU 训练、代理验证和反演
```

本地仓库路径由用户实际 clone 位置决定，不得沿用工作站路径。每次任务开始时必须从当前 Git 仓库自动解析真实 root，不得假设 `/home/Projects/MyFEniCS-Surrogate` 一定存在。

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
branch = codex/only-one-13p5nm-surrogate-inversion
upstream = origin/codex/only-one-13p5nm-surrogate-inversion
```

禁止：

- 在 `master`、Task035d 或任何其他分支开发、提交或推送；
- `git switch` / `git checkout` 到其他分支；
- 未经用户本轮明确授权，merge、rebase 或 cherry-pick `master`、Task035d 或其他研究分支；
- `git push --all`、`--mirror`、`--force`、`--force-with-lease`、`--no-verify`；
- 删除远程分支、修改或删除 `.git/hooks`、修改 branch/upstream/push 保护配置；
- 将本支线自行合入 `master`。

即使 `master` 或 Task035d 后续前进，本支线也不得自动同步。前向模型升级必须作为独立、可审查的迁移任务处理。

## 3. 主线最小侵入原则

本支线应尽量新增隔离模块，不直接重写主线正在发展的核心代码。推荐边界：

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

输入至少应支持当前求解器真实可接受的：

- 波长，当前正式范围固定为 13.5 nm；
- 几何参数；
- 材料复折射率或等价介电参数；
- 入射角、方位角和偏振；
- 网格、阶次和求解器配置；
- 需要输出的 observable 集合；
- 运行身份、随机种子和 artifact 目录。

输出必须是结构化记录，至少包含：

```text
source_branch
source_sha
parameter_vector
parameter_schema_version
geometry/material/mesh/solver config hashes
observable_schema_version
R/T/A
selected diffraction channels
true residual and physics gates
DoF/rows/NNZ
runtime and process-tree peak memory
status = measured/derived/predicted/not_run/failed/controlled_stop
artifact paths and hashes
```

任何未通过 full explicit true residual 和任务规定物理 Gate 的结果，不得进入正式训练集。

## 5. 数据集不可混源

一个正式数据集版本只能绑定一个前向求解器完整 SHA 和一个 observable schema：

```text
dataset_v1 -> forward_solver_sha = one exact full SHA
dataset_v2 -> future approved forward solver SHA
```

禁止将不同源码 SHA、不同物理定义或不同 observable schema 的样本静默混入同一数据集。升级前向模型时，必须冻结旧数据集、建立新版本，并在固定 anchor 参数点上比较新旧结果。

## 6. 本地平台与环境规则

正式本地前向计算必须运行在 Windows 电脑上的原生 WSL2 Ubuntu Linux 文件系统中。仓库、虚拟环境、缓存和数据 artifact 均不得放在 `/mnt/c`、`/mnt/d` 或 Windows 网络映射目录中执行正式 FEM。

Docker 不再是本支线的正式执行后端。Docker Desktop、旧 Docker WSL distributions、镜像、volume 和缓存的卸载必须按当前任务书分阶段执行：

1. 先审计现有 Docker 数据和其他项目依赖；
2. 记录需要保留或明确允许删除的内容；
3. 在用户明确确认卸载范围后执行；
4. 不得把 `docker-desktop-data`、其他 WSL distribution 或用户文件误删；
5. 不得在未备份/确认时使用破坏性清理命令。

新 Ubuntu 环境必须独立资格化。Python、MPI、PETSc/petsc4py、SLEPc/slepc4py、DOLFINx、Basix、UFL、FFCx 和 dolfinx_mpc 必须属于同一 complex ABI 栈。

本支线必须拥有项目本地 `.venv`；不得使用 Windows Python、Windows MPI 或全局 pip 覆盖系统组件。每次正式命令必须在同一个 WSL shell 中完成：

```text
cd -> root/branch gate -> activation -> ABI preflight -> cache override -> actual command
```

## 7. 16 GB 本地资源纪律

本地机器物理内存约 16 GB，因此默认：

```text
max_parallel_forward_solves = 1
OMP_NUM_THREADS = 1
OPENBLAS_NUM_THREADS = 1
MKL_NUM_THREADS = 1
NUMEXPR_NUM_THREADS = 1
```

任何 FEM 前必须记录：

- 物理内存与可用内存；
- swap 配置和当前使用；
- 预计 DoF、rows、NNZ；
- 求解器类型；
- 是否启用 OOC；
- scratch 可用空间；
- 终止阈值和进程树清理方式。

不得把 swap 中存活等同于可接受计算。若持续换页、系统失去响应风险、OOC scratch 不足或进程树峰值接近安全上限，应受控停止。

`p6/h10` 是资格化可行性目标，不是预设一定能在 16 GB 上完成。必须从轻量 smoke、低阶/粗网格、assembly-only 或预估 Gate 逐级推进；不能通过资源 Gate 时应保留真实 blocker，不得反复强行重跑。

## 8. 进程安全

禁止使用：

```text
killall python
pkill -f python
killall mpiexec
pkill -f mpiexec
rm -rf /tmp/myfenics-*
wsl --shutdown   # 当 Codex 当前仍有需要保留的其他 WSL 进程时
```

watchdog 只能终止自己创建并记录的 PID/process group。PID、日志和临时目录必须按 run_id 隔离。

## 9. 可执行程序封装原则

最终用户入口应尽量做到“一条命令输入参数并得到结构化结果”，但不得把不可行的打包方案写成成功。

必须区分：

1. **Linux CLI**：在 WSL Ubuntu 内运行，最可靠，优先实现；
2. **Windows launcher `.exe`**：Windows 侧只负责校验参数并调用 `wsl.exe -d <Ubuntu> -- <Linux CLI>`，可作为推荐桌面入口；
3. **真正单文件原生 Windows `.exe`**：若依赖 Linux PETSc/MPI/DOLFINx，则通常不可直接由 PyInstaller 等工具完整封装。只有实验证明 ABI、动态库、MPI 和 JIT 均可工作时才能宣称支持。

不得为了得到一个表面上的 `.exe` 而复制求解器、删掉 MPI/PETSc 功能、隐藏外部运行时依赖或降低数值可信度。

## 10. 工作站阶段

正式训练数据生成完毕后，数据集通过 manifest、hash 和 source SHA 固定，再传到工作站。工作站阶段默认不运行 FEM，只进行：

- GPU surrogate training；
- validation / uncertainty；
- inversion；
- 少量经明确授权的独立 FEM anchor 验证。

每次正式训练必须记录 GPU、框架版本、CPU 线程、DataLoader worker、峰值 GPU/主机内存、数据集身份、source SHA 和 seed。

## 11. Task 闭环

每个 surrogate task 使用独立目录：

```text
surrogate_tasks/taskNNN_<name>/
    README.md
    task.md
    outcomes/summary.md
    outcomes/test_summary.md
    response_vN.md
```

Codex 每轮结束后只提交并推送本执行分支，报告 repository root、branch/upstream、完整 HEAD、changed paths、测试、数值和资源证据、数据集/artifact 身份、未完成项与 controlled stop。未经用户明确授权，不得开始下一 Task、合入 master 或升级前向求解器基线。
