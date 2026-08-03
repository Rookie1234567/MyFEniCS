# Task004 Response V8：Required M4I training-only controlled negative

## 1. 执行边界

本轮先执行 `git pull --ff-only` 并完整阅读 Review V7。严格执行 Required M4I：
只使用不可变 train112、冻结 outer folds、已有 training OOF 和两个
response-blind angle designs；没有运行任何新的 training FEM、第二轮主动学习、
blind FEM、Task003 frozen validation、Fisher、geometry sensitivity 或 inversion。

M4I 只保留 Q1 local Matérn k24、Q2 latent median 和 S1 pre-frozen risk rule。
实现及其独立 checker 的 clean SHA 为：

```text
4884c25a4d8953bbc86f3aaabd0e2d55bb62345c
```

固定身份如下：

| identity | value |
|---|---|
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| dataset | `task004_angle_nominal_p5_ny4_train112_v1` |
| training rows | 112 |
| training tuple SHA256 | `00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68` |
| validation response accessed | `false` |
| new FEM / blind FEM | `0 / 0` |

## 2. M4I 修正与结果

每个 predictor、每个 outer fold 均独立拟合 source-only threshold；fallback
永远不能通过；从固定 quantile grid 的 source-Gate-passing candidates 中选
最高接受率者。最后把每折成功 quantile 的中位数冻结为 final quantile，并在
统一全 OOF q05/q95 normalization 下重建 production threshold。Q1/Q2 的 final
quantile 都是 `0.85`，unified threshold 为 `0.5529775444799786`。

接受分布区间使用 source accepted rows 的 targetwise finite-sample 95%
conformal residual quantile。两个 predictor 的 coverage 均达到 0.90 下限，
且每个 target 的 p95/max half-width 均分别不超过 0.02/0.03；因此 interval
Gate 通过。

| pair | cross-fit accepted | candidate pool | blind preaccepted | point accuracy | 其余 Gates |
|---|---:|---:|---:|---|---|
| Q1 Matérn k24 + S1 | 92/112 | 4013/4096 | 22/24 | fail | pass |
| Q2 latent median + S1 | 91/112 | 4013/4096 | 22/24 | fail | pass |

Q1 的 `R_total/T_total/A_balance` max absolute error 为
`0.035889638/0.037588537/0.067467046`；Q2 为
`0.009456919/0.037575777/0.044913575`。冻结 max-error 上限是 `0.03`，且
Q1 的 `A_balance` NRMSE=`0.016954577`、Q2 的 `A_balance` NRMSE=`0.010323225`
也超过 `0.01`。这是真实的 accepted cross-fit point-accuracy failure，不能
通过改变 threshold、删 target、放宽 Gate 或使用 blind response 修复。

M4I 输出：

```text
SELECTIVE_THRESHOLD_CORRECTION.json
SELECTIVE_CONDITIONAL_CONFORMAL.json
SELECTIVE_MODEL_COMPARISON_V2.json
SELECTIVE_OOF_V2.json
SELECTIVE_ACCEPTANCE_DOMAIN_V2.json
```

独立 Case130 checker 重新计算 raw risk normalization、source thresholds、
accepted sets、conformal intervals、metrics 与 candidate/blind hashes，返回：

```text
status = pass
qualification_status = controlled_negative
model_lock_created = false
blind_fem_run = false
validation_response_accessed = false
```

## 3. 停止决定

由于 Q1/Q2 都未通过完整 M4I training-only Gate，不创建
`ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK.json`，不运行 24 个 blind FEM，
不生成 validation package，也不恢复后续 FEM 或 active learning。Task004
aggregate selective surrogate 以 controlled negative 停止，Order Level B 仍为
`not_qualified`，等待 ChatGPT Review V8。

证据索引：

- `outcomes/m4i_selective_qualification.md`
- `outcomes/test_summary_v8.md`
- `outcomes/SELECTIVE_THRESHOLD_CORRECTION.json`
- `outcomes/SELECTIVE_CONDITIONAL_CONFORMAL.json`
- `outcomes/SELECTIVE_MODEL_COMPARISON_V2.json`
- `outcomes/SELECTIVE_OOF_V2.json`
- `outcomes/SELECTIVE_ACCEPTANCE_DOMAIN_V2.json`
- `benchmarks/cases/130_task004_selective_interval_correction/records/case130_check.json`
