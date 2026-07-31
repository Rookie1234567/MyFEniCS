# Task002 Review V8 Addendum：Task003 本机 CPU 执行授权

## 1. 修订结论

```text
addendum_status = approved
applies_to = Task003 only
execution_machine = local_16GB_WSL2_laptop
training_backend = CPU
GPU = not_required
workstation_transfer = not_required
production_dataset = task002_m4e_p5_ny4_112_v3
training = 96
frozen_validation = 16
formal_angle_DOE = still_forbidden
formal_inversion = still_forbidden
```

用户已明确决定 Task003 不转移到工作站，而是在生成 Case119 数据的本机 WSL2 环境中完成代理模型构建与资格化。本修订只改变 **训练执行位置与 M0 数据移交流程**，不改变 Review V8 已批准的数据身份、模型候选、冻结验证规则、误差 Gate 或停止边界。

本修订优先于以下旧的默认表述：

- `surrogate_tasks/AGENTS.md` 中“数据生成后转到工作站训练”的默认硬件分工；
- Task003 `task.md` 中 M0.3 的跨机器传输要求；
- Task003 README 中“转移到工作站”的表述。

上述覆盖仅适用于 Task003。工作站保留为未来可选的重复训练、性能对照或更大模型阶段，不是本轮前置条件。

---

## 2. 为什么本机可以完成

当前正式训练规模为：

```text
input dimension = 4
training samples = 96
frozen validation samples = 16
```

精确 Gaussian Process 对每个标量 target 的核矩阵仅为：

```text
96 x 96
```

Task003 即使对多个 aggregate、latent coefficient 或固定衍射通道分别建模，也应采用 **逐通道或小批次顺序训练**，而不是同时并行启动大量优化器。因此 16 GB 内存和 CPU 足以完成：

- degree-2 / degree-3 PCE 或 Chebyshev 基准；
- Matérn-5/2 ARD exact GP；
- deterministic 5-fold training-only CV；
- frozen-validation 一次性评分；
- 模型打包与 CLI 测试。

GPU 不会改变 96 点 exact-GP 的科学结论，也不是必要依赖。不得因为本机无 GPU 而改用神经网络、近似 GP 或降低验证标准。

---

## 3. 修订后的 M0

### M0-L1：数据保持在本机

实际数组已经位于数据生成电脑：

```text
benchmarks/artifacts/cases/119/m4e/compact_dataset/
```

Task003 不再要求 `scp`、`rsync` 或工作站解包。开始训练前必须在本机：

1. 根据 Case119 tracked manifest 重新验证全部文件 SHA256；
2. 验证 dataset ID、source SHA、sample count、array shape/dtype、sample IDs hash 和 split hash；
3. 建立只读或逻辑不可变的本地输入快照；
4. 生成 `LOCAL_DATASET_VERIFICATION.json`；
5. 证明训练代码不会原地修改 Case119 数组。

允许为了不可变性和备份在本机生成：

```text
task002_m4e_p5_ny4_112_v3.tar.zst
PACKAGE_MANIFEST.json
PACKAGE_SHA256.txt
```

但该打包不再是跨机器传输前置条件。若原始 `.npy` 不存在或 hash 不匹配，必须 controlled stop；不得无理由重跑 112 个 FEM。

### M0-L2：独立 CPU 环境

创建独立环境，例如：

```text
.venv-surrogate-cpu
```

不得修改正式 FEM `.venv` 的 PETSc、DOLFINx、MPI、Basix、UFL 或 complex ABI 栈。

CPU 环境至少记录：

```text
OS / WSL version
Python
NumPy / SciPy
scikit-learn and/or selected GP framework
BLAS backend
CPU model and logical cores
thread limits
random seeds
peak RSS
wall time
```

默认不安装 CUDA，不把 PyTorch GPU 可用性作为 Gate。若采用 GPyTorch，必须显式使用 CPU；对于当前规模，优先选择实现简单且可审计的 CPU exact-GP 后端。

### M0-L3：资源纪律

默认：

```text
OMP_NUM_THREADS = 1
OPENBLAS_NUM_THREADS = 1
MKL_NUM_THREADS = 1
NUMEXPR_NUM_THREADS = 1
max_parallel_model_fits = 1
```

可以先对一个 aggregate target 测试 1 与 2--4 个 CPU 线程；只有结果完全一致且 wall time 有明确收益时，才冻结较高线程数。不得同时并行训练几十个通道。

资源 Gate：

```text
training process peak RSS must be measured
no swap growth attributable to Task003
no uncontrolled multiprocessing
model fit must be deterministic under frozen seed
```

若某种 latent/multi-output 实现异常占用内存，应回退到顺序 independent exact GP 或更简单的训练内验证表示，而不是把工作转移到 GPU 作为默认解决方案。

---

## 4. 模型路线不变

继续只允许：

1. degree-2 / degree-3 Sparse Chebyshev 或 PCE 基准；
2. Matérn-5/2 ARD exact GP 主模型；
3. 条件式复振幅 real/imag 代理。

不得增加无边界 model zoo。不得因为 CPU 执行而修改：

- 96/16 split；
- training-only 模型选择；
- `MODEL_SELECTION_LOCK.json`；
- frozen-validation 一次性解封规则；
- aggregate、order-power、mask、ledger 和 uncertainty Gate；
- 主动加点最多 24 个的预算；
- Case119 FEM source SHA；
- 正式角度 DOE 和反演禁令。

---

## 5. 修订后的交付

Task003 应增加：

```text
outcomes/local_cpu_environment.md
outcomes/local_dataset_verification.md
records/LOCAL_DATASET_VERIFICATION.json
records/CPU_TRAINING_RESOURCE_SUMMARY.json
```

模型 manifest 必须标记：

```text
training_device = cpu
training_machine_role = local_data_generation_laptop
GPU_used = false
```

Task003 完成后仍须停止等待审阅，不得自行进入正式 angle DOE 或参数反演。
