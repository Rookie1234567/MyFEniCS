# Task006 Response V1：M0–M2 fixed-illumination h/w surrogate

## 执行结论

本轮按 Task005 Review V2 和 Task006 task book 执行，已完成 Task005
derived-only metadata closeout、Task006 M0、M1、M2，并在 training-only
边界停止等待审阅。没有运行 12 个 blind geometries，没有主动加点，没有
正式反演，也没有读取 Task003 frozen validation。

Task005 closeout 保留了 V1/V2 lock、原始/派生数据包和所有原始证据不变。
Task006 的 37-geometry dataset 由 79 个新 FEM 和 32 个 exact reuse 组成，
所有正式记录绑定固定 forward SHA `fdf961545f217d620e22800f2704ae9913a6d270`。

## 固定身份与数据

```text
dataset_id                 = task006_fixed_A05_A07_A09_hw_train37_p5_ny4_v1
forward_solver_sha         = fdf961545f217d620e22800f2704ae9913a6d270
model_id                   = S_PROD_FULL3D_STATIC_P5_H10_NY4
solver_route_id            = full3d_static_uniform_n1curl_p5_h10_ny4
observable_schema          = task002.fixed-n0-orders.v3
mesh                       = (6,4,14)
MUMPS ICNTL(14)            = 40
MPI / threads              = 2 / 1
angles                     = A05=(2°,0°), A07=(2°,90°), A09=(4°,60°)
training / blind geometries = 37 / 12
new FEM / exact reuse      = 79 / 32
blind_response_accessed    = false
validation_target_accessed = false
formal_inversion           = false
```

dataset manifest SHA256 为
`f36ffe992efe44f89c51bcac35e68145256e80979810d60ae5437686fd91cf84`；training
geometry tuple SHA256 为
`7948b6612e8350be1b6fd26aca010036016681f0484f4aa02b56c353f694bb28`。

## M2 训练-only 结果

S0 使用 log-ratio latent 并以 softmax 恢复 composition；S1 使用冻结的
m=0 primary channel、side totals 和 residual-other fractions。候选比较采用
geometry-grouped 五折 CV；每一折同时留出一个 geometry 的三个固定照明。

Matérn-5/2 ARD exact GP 和 degree-2 orthogonal trend + GP residual 通过全部
forward/uncertainty Gate；由 training selection score 选出
`matern52_ard_exact_gp`，不是硬编码。其 minimum 95% OOF coverage 为 1.0，
p95 interval half-width / N1 sigma 为 0.966271。其余 Legendre degree 2/3/4
和 local RBF 至少有一个 coverage、precision 或 width Gate 未通过，详情见
`outcomes/TRAIN37_MODEL_COMPARISON.json`。

GP 每折使用 8 个确定性 optimizer starts，并保存 fitted kernel、LML、边界
碰撞、warning 和 optimizer status。运行时出现的 `ConvergenceWarning` 被
记录到 fit metadata 并重新发出，没有静默删除。

## Synthetic recovery Gate

选定候选只用 outer-training fit，在 37 个 outer-test geometry 上完成
synthetic S1/N1 recovery。固定 coarse-grid + multiple-start bounded optimizer
的结果为：

```text
p95 |height error| = 0.000677341 nm
p95 |width error|  = 0.000137901 nm
max |height error| = 0.000986796 nm
max |width error|  = 0.000217014 nm
rejected           = 0 / 37
```

L-BFGS-B 在部分边界点的 line-search 状态由 bounded Powell 作为显式第二
优化器复核；只有显式 success 才计为通过。没有通过删除失败点或放宽恢复
Gate 的方式得到上述结果。

## Checker、测试与代码身份

Case135 M0 checker、Case136 M1 checker、Case137 train37 dataset checker 和
Case138 M2 independent checker 均通过。Case138 checker 独立确认六候选集、
selected-from-training-CV、555 条 selected OOF 行、cross-fitted uncertainty、
37 条 synthetic recovery、physics fields 以及 no-blind/no-validation 约束。

本轮新增/修改的主要 tracked evidence 为：

```text
src/surrogate/task006/surrogate.py
benchmarks/cases/138_task006_training_cv/checker.py
benchmarks/cases/138_task006_training_cv/records/case138_check.json
benchmarks/cases/138_task006_training_cv/records/case138_run.json
surrogate_tasks/task006_fixed_illumination_hw_surrogate/README.md
surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/summary.md
surrogate_tasks/task006_fixed_illumination_hw_surrogate/response_v1.md
surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TRAIN37_*.json
```

M2 输出是 training candidate evidence，不是正式 model lock。下一步是否运行
blind12 必须等待新的审阅授权；本轮执行到此停止。

M2 的 source/file identity 保存在
`outcomes/M2_IMPLEMENTATION_IDENTITY.json`；其中记录了 M2 前基线
`71593f3ab11d58cd919a66c00319dc619be9bdc9`、当前训练源文件和独立 checker
的 SHA256，以及 dataset manifest SHA256。
