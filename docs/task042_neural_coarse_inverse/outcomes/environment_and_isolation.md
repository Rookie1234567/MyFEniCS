# Git、环境和共享资源隔离

## Git 现场准备

NN-Lab 在宿主机上是真实空目录、非 symlink、未登记；沙箱最初显示的空 `.git/.agents/.codex` 是保护占位。第一次防御性断言在任何写入前退出，随后宿主机核验后才操作。没有删除或覆盖这些目录，也没有独立 clone。

核验 `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` 是 bare canonical，origin 为 `github-myfenics:Rookie1234567/MyFEniCS.git`，别名解析到 GitHub 的 git/BatchMode/严格hostkey。非交互 ls-remote 实读本任务头为 `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7`。fetch 只取本任务 ref，显式 `--no-auto-maintenance --no-write-fetch-head --no-tags` 并禁用自动 maintenance/gc；没有回退历史。

原 `origin.fetch` 只映射 Task39，首次 `--track` 创建被 Git 拒绝且未产生分支/worktree。之后 `--no-track -b` 登记 NN-Lab；用户明确回复“允许仅追加 Task042 refspec 并设置 upstream”，据此只追加对应 refspec，保留原 URL/refspec，再设标准 upstream。未修改全局配置或默认配置，未在旧计算目录 checkout/switch/pull/reset/stash/clean。

| 项目 | 核验值 |
|---|---|
| pwd / Git toplevel | `/home/fenics/Projects/NN-Lab` |
| branch | `task42_neural_coarse_inverse`，逐字符一致 |
| HEAD（准备完成） | `f8c51c8e614edc806cf72120ac2cfd14ae8b62f7`，clean、ahead0/behind0 |
| HEAD（最终 clean F0 源码） | `9934c2e08d017124ba70bdc86ec0c22f39ca792f` |
| upstream | `origin/task42_neural_coarse_inverse` |
| common Git directory | `/home/fenics/Projects/Maxwell3D-Lab/task-repository.git` |
| worktree | NN-Lab 本身登记，无嵌套 MyFEniCS |
| 历史 | 冻结 base 和初始任务提交均 `merge-base --is-ancestor` 成功；未自动合并或重写 |
| 原计算 worktree HEAD | `64ca6048ca7e1fd7cc66a9b1b1fb2a858a0bd5aa`；两旧 docs detached HEAD 也保留 |

[Git 准备记录](records/git_preparation.json) 保存完整登记和 refspec。交付文档 HEAD 由最终推送后的 Git 回报给出；不能拿它替代 clean 运行源码。

## Python 与原生库

| 环境 / 进程 | 解释器、导入与实际库 | 本轮资格 |
|---|---|---|
| pure | NN-Lab `.venv/bin/python`，Python3.12.3；system-site只读 NumPy1.26.4、pytest7.4.4 | 无 PETSc/DOLFINx/MPI 动态库；[record](records/environment_pure.json) |
| FE | 同一新 `.venv`；DOLFINx0.10.0、Basix0.10.0、UFL2025.2.1、FFCx0.10.1.post0、petsc4py/PETSc3.19.6、mpi4py3.1.5 | complex128/int64/MPI1；[record](records/environment_fe.json) |
| ML | 新 `.venv-ml/bin/python`，不带system-site；Torch2.7.1+cpu、NumPy1.26.4 | CPU-only、无 FE/MPI 动态库；[record](records/environment_ml.json) |

FE 只读 prefix 为现场原 worker 实际使用的 `.../tmp/task39extra_v5_abi_restore_20260923/base`，PETSc 使用其 `prefix/pord64-overlay/petsc`；MPC共享库0.10.1路径和所有实际映射详见 record。没有 source 旧 activation、修改其 venv/prefix、安装系统包、切换BLAS alternatives或改变CUDA/驱动。MPC Python没有 `__version__` 字段，保留 null 并记录实际共享库路径，不猜造版本字段。

FE 库导入时 OpenMPI 依赖映射了系统 `libcuda.so.595.91.07`；这项真实映射保留在记录中。Task042 没有创建 CUDA context、调用GPU算子或训练；ML进程只映射自己的 CPU Torch/OpenBLAS，未把这套运行库注入 FE。Torch 默认 dtype 仍为float32，此轮没有模型；后续训练/推理必须显式设置 float64 实虚通道并单独核验，不能把“安装CPU Torch”称为FP64模型资格。

所有 `src.__file__` 和新协议模块路径均为 NN-Lab。`.venv` 是新建 system-site环境，只读复用发行版 Python 包；不是原任务 .venv 的链接或复制。独立 ML固定顶层依赖和解析后的所有版本分别见 [requirements](../../../input/task042_neural_coarse_inverse/requirements-ml.txt)、[lock](../../../input/task042_neural_coarse_inverse/requirements-ml.lock.txt)。首次安装整树峰190,951,424 B、54.551683 s、swap0；没有下载GPU运行时或大型模型。

## 可写路径

[activation](../../../scripts/activate_task042.sh) 显式清除继承的 Python/动态库/PETSc/旧资格和资源变量，按 pure/fe/ml分模式配置。`PYTHONNOUSERSITE=1`，所有数学线程1，F0 `CUDA_VISIBLE_DEVICES=''`。创建前用 realpath 检查 symlink 逃逸。

| 数据 | NN-Lab 内独立路径 |
|---|---|
| results | `results/task042` |
| artifacts | `benchmarks/artifacts/task042` |
| TMP / TEMP | `tmp/task042/<mode>/tmp` |
| XDG cache / config | `tmp/task042/<mode>/xdg` / `config` |
| 实际 FE JIT | `tmp/task042/fe/xdg/fenics`；通过 `dolfinx.jit.get_options()` 实读 |
| Python bytecode / Matplotlib | `tmp/task042/<mode>/pycache` / `matplotlib` |
| Torch / HF model cache | `tmp/task042/<mode>/torch` / `huggingface` |
| Triton / CUDA / Numba / pip / uv / Ruff | 对应 `tmp/task042/<mode>/...` |

本轮JIT目录没有生成form内核；原任务的大型结果、因子和运行缓存未复制。Git ignored核验和 raw SHA见测试摘要。

新venv最初bootstrap的临时路径与资源没有单独记录，不追认该未采样准备步骤的全过程缓存/时间资格。activation之后的依赖安装、所有测试/导入和输出路径均实际核验并保留记录；后续运行应先激活再执行。

## 资源与真实停止条件

宿主机一次轻量快照（2026-09-28T08:57:36.348903+00:00）确认原 worker341839/start_ticks17197130仍运行，CPU24、RSS1,149,927,038,976 B、swap0；parent341799为CPU9，observer341987为CPU10。Metrology两个GPU worker509439/509440为CPU25–32，两卡100%。CPU14的物理thread siblings只含14，用于本任务轻测试。绑核不能证明共享内存带宽绝对零竞争。

MemTotal2,163,100,385,280 B、MemAvailable988,837,916,672 B、NN-Lab磁盘自由3,456,128,942,080 B；全机swap已有1,224,704 B，只有诊断含义，不归因 Task042。即使可用内存充足，存在heavy仍阻止F1–F5。

前台薄封装复用 `benchmarks.subreaper_watchdog.supervise`：单核、math threads1、整个专用父及后代RSS hard2GiB/warning1.5GiB、own VmSwap非零停止、全机swap只诊断。有限 wall预算用于 F0 import/tests（180 s）和一次依赖安装（600 s），不是新的PDE预算。监督只处理自身后代，所有已运行树正常清场；没有改旧 watchdog、PSS策略、CPU/NUMA或发送邻任务信号。没有后台等待器、锁占位或自动启动脚本。
