# Task003：p5/Ny4 单保真代理模型构建与资格化

## 状态

```text
status = ready_for_codex_execution
review_authority = Task002 review_report_v8.md + review_report_v8_local_cpu_addendum.md
input_dataset = task002_m4e_p5_ny4_112_v3
training = 96
frozen_validation = 16
production_forward_model = S_PROD_FULL3D_STATIC_P5_H10_NY4
execution_machine = local 16 GB WSL2 laptop
training_device = CPU
GPU_required = false
workstation_transfer = not required
formal_angle_DOE = forbidden
formal_inversion = forbidden
```

## 目标

使用已经通过 Case119 资格化、且当前就位于数据生成电脑上的 Ny4 compact dataset，建立一个可调用、带不确定度和物理约束的 S 偏振四维前向代理：

```text
(height_nm, width_x_nm, grazing_deg, azimuth_deg)
    -> aggregate R/T/A
    -> fixed-order outgoing S/P powers
    -> prediction uncertainty
    -> analytic power-carrying mask / domain status
```

复振幅代理作为本 Task 的条件式第二层目标；不得为了强行支持相位而降低功率代理的可信度。

## 本机 CPU 执行修订

用户已明确授权本 Task 在本机完成，不再转移到工作站。当前只有 96 个训练样本、四维输入；每个标量 exact-GP 的核矩阵仅为 `96 x 96`，本机 CPU 和 16 GB 内存足够完成 PCE、Matérn exact GP、训练内交叉验证和一次性冻结验证。

正式执行要求：

```text
surrogate environment = .venv-surrogate-cpu
FEM environment = 不修改
GPU/CUDA = 不要求
model fits = 默认逐通道顺序执行
BLAS/OMP oversubscription = 禁止
peak RSS / swap / wall time = 必须记录
```

Task003 的本机执行权威为：

```text
Task002 review_report_v8_local_cpu_addendum.md
Task003 task_local_cpu_addendum.md
```

它们仅覆盖原任务书中的工作站移交和 GPU 表述；数据身份、模型范围、验证 Gate 和停止边界保持不变。

## 开始前必须阅读

1. 根目录 `AGENTS.md`；
2. `surrogate_tasks/AGENTS.md`；
3. Task002 `review_report_v8.md`；
4. Task002 `review_report_v8_local_cpu_addendum.md`；
5. Task002 `response_v8.md`；
6. Task002 `outcomes/m4e_ny4_production.md`；
7. Task002 `outcomes/m4e_dataset_report.md`；
8. 本目录 `task.md`；
9. 本目录 `task_local_cpu_addendum.md`。

## 数据边界

Git 中只保存数据身份、hash、checker 和报告。实际数组已经位于本机 ignored artifact：

```text
benchmarks/artifacts/cases/119/m4e/compact_dataset/
```

Task003 第一阶段不再跨机器传输，而是在本机逐文件复核 Case119 hash，建立只读/逻辑不可变输入快照，并生成 `LOCAL_DATASET_VERIFICATION.json`。不得假设 clone 远程分支即可得到 `.npy` 数据，也不得无理由重跑 112 个 FEM。

若实际数组不存在或 hash 不一致，必须 controlled stop；不能重新生成一个“看起来相同”的数据集替代。

## 模型路线

只允许：

```text
baseline = degree-2 / degree-3 Sparse Chebyshev or PCE
primary = Matérn-5/2 ARD exact GP on CPU
conditional second tier = complex amplitude real/imag surrogate
```

96 点规模不需要神经网络、近似 GP 或 GPU。不得开展无边界 model zoo。

## 主要交付

```text
src/surrogate/
benchmarks/cases/120_task003_surrogate_training/
surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/
    outcomes/summary.md
    outcomes/test_summary.md
    outcomes/local_cpu_environment.md
    outcomes/local_dataset_verification.md
    outcomes/model_selection.md
    outcomes/frozen_validation.md
    response_v1.md
```

模型包必须绑定 dataset ID、dataset file hashes、训练代码 SHA、CPU/BLAS 环境、线程设置、seed、输出合同、资源记录和验证指标。

## 停止边界

Task003 完成后停止等待 ChatGPT 审阅。不得自行开始正式 angle DOE、实验反演、MCMC、P incident surrogate 或前向 FEM 基线升级。
