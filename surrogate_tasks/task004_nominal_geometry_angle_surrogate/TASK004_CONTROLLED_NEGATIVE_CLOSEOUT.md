# Task004 controlled-negative closeout

## 结论

依据 `review_report_v8.md`，Task004 正式关闭为：

```text
Task004_status = closed_controlled_negative
full-domain aggregate surrogate = controlled_negative
selective aggregate surrogate = controlled_negative
order-resolved surrogate = not_qualified
```

这不是程序卡死、资源不足或前向求解失败。M4I 已完成 Review V7 要求的
predictor-specific threshold、no-fallback、highest-acceptance quantile、统一
OOF normalization 和 accepted-distribution conformal interval 修正；两个允许的
predictor 的区间 Gate 通过，但严格 cross-fitted accepted OOF 的冻结点精度 Gate
仍未通过。因此不再通过同一 OOF truth 调整规则、阈值、模型或 Gate。

## 不可变身份

| identity | value |
|---|---|
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| M4I implementation SHA | `4884c25a4d8953bbc86f3aaabd0e2d55bb62345c` |
| dataset | `task004_angle_nominal_p5_ny4_train112_v1` |
| training rows | 112 |
| training tuple SHA256 | `00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68` |
| fixed geometry | `h=120 nm, w=17 nm` |
| forward route | `Full3D static uniform N1curl p5/h10/Ny4`, MPI2, thread1 |
| MUMPS | `ICNTL(14)=40` |
| observable | `task002.fixed-n0-orders.v3` |

## 资格与 Case130 语义

M4I 只保留 Q1 local Matérn k24、Q2 latent median 和 S1 pre-frozen risk rule。
Q1/Q2 的 accepted cross-fit OOF 分别为 `92/112` 和 `91/112`，candidate pool
均为 `4013/4096`，blind design response-blind preacceptance 均为 `22/24`。
两者仍违反冻结点精度上限，因而没有任何 predictor/rule pair 获得资格。

Case130 checker 的结果是：

```text
checker status = pass
qualification status = controlled_negative
```

这里的 `pass` 只表示 checker 独立重算了数据身份、fold、threshold、accepted
set、conformal interval、hash 和 fail-closed 状态；它不表示代理模型通过科学
资格 Gate，也不表示模型锁存在。

## Blind validation 状态

```text
blind design = 24 points
blind responses measured = 0 / 24
blind FEM = intentionally_not_run
```

由于 M4I 没有创建任何 model-selection lock，24 个 blind FEM 没有被授权，且
不会在 Task004 closeout 中补跑。不存在可用于事后调参的 blind response、blind
validation package 或 blind qualification 结论。

## 证据保留

以下内容保持原样并继续作为权威证据：

- `train112` immutable dataset、manifest、file hashes 和 frozen folds；
- Case124–Case130 的 checker、配置、记录和负结果；
- M4I 的 threshold、conformal、OOF、acceptance-domain 和 comparison artifacts；
- 早期 M4H、M4E2、spatial-support、learning-curve 和所有 controlled-negative 文档。

本轮没有删除、覆盖或重跑这些证据。完整入口见
`TASK004_FINAL_STATUS.json`、`outcomes/summary.md` 和
`outcomes/m4i_selective_qualification.md`。

## 关闭后的边界

Task004 不再允许：

- 任何新的 Task004 FEM 或第二轮 active learning；
- 继续训练模型、改变 threshold、改变 Gate 或增加 model family；
- 运行 Task004 blind validation；
- 在没有新任务书和新审阅的情况下开始 Task005 FEM。

Review V8 建议的后续方向是另建独立的离散 illumination sensitivity / Fisher
DOE 任务。该建议不构成当前任务授权；本 closeout 到此停止。
