# Task004 M4I 选择性 aggregate 资格结果

## 执行边界与身份

M4I 只读取不可变 `train112`、冻结五折、已有训练 OOF，以及
response-blind 的 `candidate_pool` 和 `blind_design`。本轮没有运行新的
training FEM、blind FEM 或第二轮主动加点，没有读取 Task003 frozen validation。

| identity | value |
|---|---|
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| dataset | `task004_angle_nominal_p5_ny4_train112_v1` |
| training rows | 112 |
| training tuple SHA256 | `00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68` |
| M4I implementation SHA | `4884c25a4d8953bbc86f3aaabd0e2d55bb62345c` |
| validation response accessed | `false` |
| new FEM / blind FEM | `0 / 0` |

M4I 只保留两个 point predictor：`Q1=L2_local_matern_k24` 和
`Q2=E1_latent_median_ensemble`；风险规则只有冻结的
`S1_pre_frozen_m4e2_ensemble`。RBF 仅作为 S1 的 disagreement 输入，不再
作为 point predictor；S2 不再参加资格比较。

## 阈值修正

每个 predictor、每个 outer fold 都用另外四折 source rows 独立拟合 q05/q95
normalization，按固定网格
`0.50,0.60,0.65,0.70,0.75,0.80,0.85,0.90,0.95` 检查 source Gate，并选择
接受率最高的通过候选。若没有通过候选则标记
`threshold_not_qualified`，没有 fallback；本次两个 predictor 的五折均为
`no_fallback=true`。

| predictor | 五折 source quantile | 五折 source accepted count | final unified quantile | final unified threshold |
|---|---|---|---:|---:|
| Q1 Matérn k24 | 0.85, 0.85, 0.80, 0.80, 0.95 | 75, 76, 72, 72, 84 | 0.85 | 0.5529775444799786 |
| Q2 latent median | 0.85, 0.85, 0.80, 0.80, 0.90 | 75, 76, 72, 72, 80 | 0.85 | 0.5529775444799786 |

最终阈值不是各折数值阈值的平均，而是在全部 OOF risk 上统一 q05/q95
normalization 后，使用冻结的 final quantile 重新计算。该过程并报告了
cross-fit OOF 与 full-trained response-blind screening 的分布漂移。

## Training-only Gate

| pair | cross-fitted accepted OOF | unified OOF accepted | candidate pool | blind-design preaccepted | 结果 |
|---|---:|---:|---:|---:|---|
| Q1 Matérn k24 + S1 | 92/112 = 0.821429 | 0.848214 | 4013/4096 = 0.979736 | 22/24 | controlled negative：point accuracy fail |
| Q2 latent median + S1 | 91/112 = 0.812500 | 0.848214 | 4013/4096 = 0.979736 | 22/24 | controlled negative：point accuracy fail |

冻结点精度 Gate 为每个 target 同时满足 NRMSE ≤ 0.01、p95 absolute ≤ 0.01、
max absolute ≤ 0.03。预测结果如下：

| pair / target | NRMSE | p95 abs | max abs |
|---|---:|---:|---:|
| Q1 / `R_total` | 0.006426906 | 0.003352608 | 0.035889638 |
| Q1 / `T_total` | 0.009335989 | 0.007049532 | 0.037588537 |
| Q1 / `A_balance` | 0.016954577 | 0.008558446 | 0.067467046 |
| Q2 / `R_total` | 0.002600732 | 0.002724782 | 0.009456919 |
| Q2 / `T_total` | 0.007524943 | 0.005770360 | 0.037575777 |
| Q2 / `A_balance` | 0.010323225 | 0.007004455 | 0.044913575 |

因此 Q1 和 Q2 都在 accepted cross-fit OOF 上违反了至少一个冻结点精度
上限；没有依据更高接受率去放宽 Gate。两者的 accepted supported-window、
composition、接受率、candidate/blind 预筛、predictor-specific threshold
和 no-fallback Gate 均通过。

## Accepted-distribution conformal interval

每折区间半宽只由该折 source accepted rows 的 targetwise absolute residual
有限样本 95% conformal quantile 得到；held-out truth 不参与阈值或区间校准。
物理 `[0,1]` clipping 只在保存未裁剪半宽后执行。

| pair | target | coverage | p95 half-width | max half-width |
|---|---|---:|---:|---:|
| Q1 | `R_total` | 0.945652 | 0.007937389 | 0.007937389 |
| Q1 | `T_total` | 0.956522 | 0.009088386 | 0.009088386 |
| Q1 | `A_balance` | 0.956522 | 0.012676029 | 0.012676029 |
| Q2 | `R_total` | 0.956044 | 0.007935435 | 0.007935435 |
| Q2 | `T_total` | 0.967033 | 0.009088379 | 0.009088379 |
| Q2 | `A_balance` | 0.967033 | 0.012676027 | 0.012676027 |

所有 coverage 均达到 0.90 下限，半宽有限、为正、p95 ≤ 0.02 且 max ≤ 0.03。
旧的 `coverage > 0.99` 只保留为 warning，不再作为 Gate；本次也没有触发
该 warning。

## 独立核验与停止

Case130 checker 不导入 M4I fitter，而是从 compact OOF 的 raw risk inputs
独立重建每个 outer fold 的 normalization、S1 risk、候选 quantile、accepted
set、conformal radius、误差和 candidate/blind index/angle hashes。checker
结果为 `status=pass`，同时明确记录 `qualification_status=controlled_negative`。

由于两个允许的 pair 都未通过完整 training-only Gate：

```text
ANGLE_AGGREGATE_SELECTIVE_MODEL_SELECTION_LOCK = absent
blind-validation FEM = not run
new training FEM = 0
Task003 frozen validation = not accessed
Order Level B = not qualified
```

不得用这 24 个 blind 设计调参或重新声称 validation；后续应等待 Review V8。
