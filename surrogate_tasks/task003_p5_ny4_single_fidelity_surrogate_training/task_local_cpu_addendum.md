# Task003 本机 CPU 执行补充任务书

## 0. 权威与优先级

本文件由用户明确授权，适用于整个 Task003，并覆盖原 `task.md` 中与工作站、GPU和跨机器数据移交有关的条款。

冲突时优先级为：

```text
Task002 review_report_v8_local_cpu_addendum.md
> 本文件
> Task003 task.md
> surrogate_tasks/AGENTS.md 中默认工作站分工
```

其余数据、模型、验证、误差和停止合同保持原 `task.md` 不变。

---

# M0-L：本机数据与 CPU 环境

## M0-L1 Git 与数据位置

仍在：

```text
branch = codex/only-one-13p5nm-surrogate-inversion
```

训练数据直接使用本机现有 ignored artifact：

```text
benchmarks/artifacts/cases/119/m4e/compact_dataset/
```

不执行工作站传输。不得把 `.npy` 加入 Git，也不得重跑 112 个 FEM。

开始前检查：

```bash
pwd
git rev-parse --show-toplevel
git remote get-url origin
git branch --show-current
git rev-parse --abbrev-ref --symbolic-full-name '@{u}'
git rev-parse HEAD
git status --short
```

## M0-L2 本地数据验证

实现一个独立于 Case119 writer 的本地验证入口，例如：

```bash
python -m src.surrogate.cli verify-dataset \
  --dataset benchmarks/artifacts/cases/119/m4e/compact_dataset \
  --case119-evidence benchmarks/cases/119_task002_p5_ny4_bulk_campaign \
  --output benchmarks/artifacts/cases/120/task003/LOCAL_DATASET_VERIFICATION.json
```

必须验证：

```text
dataset_id = task002_m4e_p5_ny4_112_v3
source SHA = 10e3356ba8364286a452077f71d7e3b92ea24cd5
sample count = 112
training = 96
frozen validation = 16
all file SHA256
array shape and dtype
sample_ids_hash
split_hash
Ny4 model/route/schema identity
```

训练代码必须以只读方式加载数据，不得原地修改原数组。

若希望建立不可变副本，可在本机生成 package 或 copy-on-write snapshot，并再次验证 hash；不是跨机器传输要求。

## M0-L3 独立环境

创建：

```text
.venv-surrogate-cpu
```

不得在 FEM `.venv` 中安装或升级代理依赖。

建议最小依赖：

```text
Python
NumPy
SciPy
scikit-learn
joblib
matplotlib（只用于报告）
```

若训练内证据表明需要 GPyTorch，可安装 CPU 版本，但必须记录原因；不得安装 CUDA 作为前置条件。

冻结并报告：

```text
pip freeze / environment lock
BLAS backend
CPU model
logical cores
thread settings
random seeds
```

## M0-L4 CPU 和内存 Gate

默认环境变量：

```bash
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
```

默认：

```text
max_parallel_model_fits = 1
```

所有输出通道顺序训练。可以把多个 target 的数据准备向量化，但不能同时启动大量独立优化器。

先运行一个 aggregate GP smoke，记录：

```text
fit wall time
prediction wall time
peak RSS
swap before/after
repeat-run metric and model-state identity
```

然后才允许完整训练。

CPU 训练不需要 watchdog 的 FEM 级强杀逻辑，但必须测量进程峰值内存；若异常增长、持续 swap 或失控多进程，应 controlled stop。

### M0-L Gate

```text
local dataset exact verification = pass
surrogate CPU environment isolated from FEM = pass
single-target CPU smoke = pass
peak memory and swap recorded = pass
frozen validation remains inaccessible = pass
```

---

# M1-L：CPU 训练实现约束

## M1-L1 PCE

PCE/Chebyshev degree 2 和 3 使用 NumPy/SciPy CPU 实现。不得使用 GPU，也不得并行穷举高阶基。

## M1-L2 Exact GP

主模型仍为：

```text
Matérn 5/2
ARD
exact GP
explicit nugget/jitter
```

96 个训练样本的标量核矩阵为 `96 x 96`。优先实现可审计、可序列化的 CPU exact GP。

推荐执行顺序：

1. aggregate composition latent targets；
2. primary order-power channels；
3. secondary channels；
4. 条件式复振幅 real/imag。

每一层达到 hard Gate 后再继续下一层，避免在不合格 target 上浪费本机时间。

## M1-L3 后端选择

训练内可以比较：

```text
scikit-learn exact GPR
或一个明确冻结的 CPU exact-GP 实现
```

不得把“scikit-learn vs GPyTorch”扩展成模型 zoo。若两者物理模型相同，只选择更简单、可复现、资源更低的实现。

任何后端比较只使用 training CV；不得读取 frozen validation。

## M1-L4 CPU 重复性

至少对选定 aggregate 模型做两次完全相同 seed 的重复训练，验证：

```text
selected hyperparameters identical or within frozen optimizer tolerance
CV predictions identical within numerical tolerance
saved/reloaded predictions identical
```

如果使用多线程优化后重复性变差，回退单线程。

---

# M2-L：原 Task003 其余阶段

原 `task.md` 的以下部分继续原样执行：

```text
M1 train-only loader and validation guard
M2 feature/target/channel contract
M3 PCE and GP training-only model selection
M4 optional active learning
M5 MODEL_SELECTION_LOCK
M6 one-time frozen validation
M7 conditional complex-amplitude qualification
M8 model package and CLI
M9 tests, reports and stop for review
```

只有以下语义替换：

```text
workstation copy exact
-> local immutable dataset verification

CPU/GPU comparison
-> local CPU repeatability/resource smoke

GPU memory
-> not applicable; record GPU_used=false
```

---

# 新增交付

至少新增：

```text
surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/outcomes/
    local_cpu_environment.md
    local_dataset_verification.md

benchmarks/cases/120_task003_surrogate_training/records/
    LOCAL_DATASET_VERIFICATION.json
    CPU_TRAINING_RESOURCE_SUMMARY.json
```

`MODEL_MANIFEST.json` 必须包含：

```text
training_device = cpu
GPU_used = false
CPU and BLAS identity
thread limits
peak RSS
training and inference wall times
```

Task003 完成后停止等待审阅。正式 angle DOE、反演、MCMC、P incident surrogate 与 FEM 基线升级仍然禁止。
