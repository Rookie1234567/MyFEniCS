# Task004 aggregate qualification v3（train112）

## 结论

16 个主动加点均通过固定前向 Gate 后，组成不可变
`task004_angle_nominal_p5_ny4_train112_v1`。在相同的五折 training-only
流程上，112 点仍未达到 Aggregate Level A，因此不创建
`ANGLE_AGGREGATE_MODEL_SELECTION_LOCK.json`，也不解封 blind validation。

## 身份

| 项目 | 值 |
|---|---|
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| model / route | `S_PROD_FULL3D_STATIC_P5_H10_NY4` / `full3d_static_uniform_n1curl_p5_h10_ny4` |
| mesh / MUMPS / MPI / threads | `(6,4,14)` / ICNTL(14)=40 / 2 / 1 |
| dataset | `task004_angle_nominal_p5_ny4_train112_v1` |
| training rows / tuple hash | 112 / `00fb746bbb881ac7fc3cd27c313b2b526bd2f69f8e89ef621f3e6d9790af5c68` |
| dataset builder SHA | `f45070c278847f43ccb01d77261dab6b1e387bb8` |
| validation target accessed | `false` |

## 标准 112 点 CV

training-only CV 在 `train112_cv/training_cv.json` 中保存了 14 个有限候选、
每折 fitted kernel、OOF prediction/std/error、region 和 cutoff 标签。按
training CV 的 selection score 选择 `gp:F3`, jitter `1e-8`；没有硬编码
`exact_gp` 或直接沿用旧候选。

| target | NRMSE | p95 abs | max abs | Level A 限值 |
|---|---:|---:|---:|---:|
| `R_total` | 0.0246633 | 0.0370765 | 0.1080872 | 0.01 / 0.01 / 0.03 |
| `T_total` | 0.0120798 | 0.0140645 | 0.0360235 | 0.01 / 0.01 / 0.03 |
| `A_balance` | 0.0332836 | 0.0329176 | 0.1101640 | 0.01 / 0.01 / 0.03 |

`R+T+A=1` 的 composition 约束保持精确，但 accuracy 三项均有超限指标；
supported-window、整体 aggregate 和 power Gate 也未同时通过。cross-fitted
uncertainty coverage 仍在规定的 0.90–0.99 区间（R/T/A 分别为
0.9464/0.9643/0.9732），这只说明不确定度校准可用，不等于精度资格通过。
显式保留的 `ConvergenceWarning` 已写入训练日志，没有被静默转换为成功。

## 96→112 配对曲线

配对比较固定原 train96 五折测试行；train112 一侧只在训练侧加入全部 16
个新点。结果见 `paired_learning_curve_96_to_112.{json,md}`：

| candidate | max abs 96→112 | max-error reduction | mean-abs reduction |
|---|---:|---:|---:|
| local RBF k24 | 0.1334965 → 0.1136339 | 0.0198626 | 0.000335060 |
| local Matérn k24 | 0.1443802 → 0.0932643 | 0.0511159 | 0.000145611 |
| local Matérn k32 | 0.1441228 → 0.1438660 | 0.000256853 | -0.000549240 |

因此加点对 k24 的最大尾部误差有改善，但尚不足以建立 aggregate model
lock；k32 的同一测试行平均绝对误差反而略增，不能挑选性地宣称全面改善。

## 受控停止

`case127_train112_check.json` 和 `case127_post_fem_check.json` 均为
`pass`。由于 Level A 未通过，后续禁止第二轮主动学习、24 个 blind FEM、
PCE/GP 以外的正式反演流程、Fisher 和 geometry sensitivity；当前停止等待
Review V5。
