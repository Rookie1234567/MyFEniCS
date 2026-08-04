# Task006 Response V2：M2R 与 blind12 受控负结果

## 执行结论

按 Review V1 完成了 M2R、Case139 deterministic replay、模型锁以及条件授权的
唯一一次 blind 批次。M2R 先在不可变 train37 上统一 S0/S1 side-total authority，
然后冻结 `legendre_3` 作为 training-only selection 结果；只有在全部 training
Gate 和 Case139 checker 通过后才创建 lock。lock 创建后使用固定 forward SHA
执行 12 个 blind geometries × A05/A07/A09，共 36 个 FEM。结果为：

```text
36 / 36 attempted
34 measured_pass
2 failed_numerical_gate
qualification_status = controlled_negative
```

因此本轮在 blind 后停止等待 Review V2。没有主动加点、正式反演、输入参数扩展、
Task003 frozen validation 访问或失败点重跑。

## M2R 合同与证据

S0 使用冻结的
`zR=log((R+eps)/(A+eps))`、`zT=log((T+eps)/(A+eps))` 和
`softmax(zR,zT,0)`。S1 只拟合 selected/other fraction；S0 预测的
`R_total/T_total` 是唯一 side-total authority。每条 OOF/盲点评估记录保留
selected、other、side total、selected+other 和 ledger residual。

本轮冻结并重新生成：

```text
TRAIN37_GEOMETRY_FOLDS.json
TRAIN37_MODEL_COMPARISON_V2.json
TRAIN37_OOF_PREDICTIONS_V2.json
TRAIN37_S1_LEDGER_V2.json
TRAIN37_UNCERTAINTY_V2.json
TRAIN37_SYNTHETIC_RECOVERY_V2.json
TRAINING_MODEL_SELECTION_CANDIDATE_V2.json
```

Case139 独立重建 transform、fold、OOF prediction hash、composition、ledger、
CV metrics 和 recovery，结果为 `status=pass`。六候选中按 training-only
selection score 选出 `legendre_3`；没有读取 blind response 来选模型。

锁文件为：

```text
surrogate_tasks/task006_fixed_illumination_hw_surrogate/outcomes/TASK006_MODEL_SELECTION_LOCK.json
status = locked_for_blind
selected_candidate = legendre_3
forward_solver_sha = fdf961545f217d620e22800f2704ae9913a6d270
model = S_PROD_FULL3D_STATIC_P5_H10_NY4
route = full3d_static_uniform_n1curl_p5_h10_ny4
mesh = (6,4,14)
MUMPS ICNTL(14) = 40
MPI / thread = 2 / 1
```

该 lock 是 blind 前的不可变身份文件；blind 结束后没有把 `blind_fem_run` 或
任何 fitted metadata 回写进去。

## Blind forward 结果

所有点都只尝试一次，runner 按锁定顺序执行且未根据中间结果改变配置。两个
失败点及其实际 Gate 如下：

| key | status | failed gate | 保持通过的 Gate |
|---|---|---|---|
| `117.5,17.25/A07` | `failed_numerical_gate` | `true_residual_le_1e-9=false` | completed direct solve、energy closure、fixed order schema、topology、n≠0 leakage、raw reflection/transmission ledger |
| `117.5,17.25/A09` | `failed_numerical_gate` | `true_residual_le_1e-9=false` | completed direct solve、energy closure、fixed order schema、topology、n≠0 leakage、raw reflection/transmission ledger |

这两个点没有 `task006_production_sample.json`；formal records、execution SHA 和
失败 Gate 被 `TASK006_BLIND_FAILURE_REPORT.json` 原样索引。没有放宽 `1e-9`、
没有跳过点、没有删除 P/S 分量、没有换模型或重跑。

34 条成功响应的锁定模型只读诊断为：

```text
S0 successful-row minimum 95% coverage = 1.0
S1 successful-row minimum 95% coverage = 1.0
composition max residual = 1.11e-16
predicted selected/other nonnegative = true
predicted selected <= S0 side total = true
predicted ledger max residual = 0.0
```

由于同一 geometry 缺少 A07/A09 两个响应，只有 11/12 个几何拥有完整三照明
synthetic recovery 输入。锁定模型在这 11 个完整几何上显式收敛，但不能把
11/12 改写为 12/12 blind recovery Gate 通过。因此整体资格明确为
`controlled_negative`。

## Case141 checker 与停止边界

`benchmarks/cases/141_task006_blind12_forward/checker.py` 不调用 runner 来
决定状态；它独立核验 36 个 key/point hash、lock hash、solver/model/schema
identity、成功 sample 的 split/source、失败 formal gates、S0/S1 预测和
recovery。输出：

```text
case141 status = pass
qualification_status = controlled_negative
failure_count = 2
blind_response_used_for_fit = false
model_tuned_after_blind = false
validation_target_accessed = false
```

这里的 checker `pass` 只说明受控负结果被完整、确定性地记录；它不等于代理
资格 Gate 通过，也不授权后续 inversion。证据入口：

```text
outcomes/TASK006_BLIND_FAILURE_REPORT.json
benchmarks/cases/141_task006_blind12_forward/records/case141_check.json
benchmarks/artifacts/cases/141_task006_blind12_forward/BLIND12_CAMPAIGN.json
```

本轮到此停止，等待 ChatGPT Review V2。除非新的任务书明确授权，不得运行新的
FEM、重复这 12 个 blind 点、主动加点、训练新代理、开始 Bayesian inversion 或
扩展输入参数。
