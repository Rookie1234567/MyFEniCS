# Task004 M4B training dataset report

本轮只重建现有 Case124 的 96 个 `measured_pass` Ny4/p5 前向记录，没有重跑 FEM，也没有打开 Task003 或 Task004 blind-validation 的 response。

| 项目 | 结果 |
|---|---|
| dataset | `task004_angle_nominal_p5_ny4_train96_v2` |
| rows | 96，精确覆盖 training design，无缺失、重复或额外点 |
| forward solver SHA | `fdf961545f217d620e22800f2704ae9913a6d270` |
| surrogate builder SHA | `0341ceeea5904aa6c44bda37a17e85bfeb8c0f33` |
| model / route | `S_PROD_FULL3D_STATIC_P5_H10_NY4` / `full3d_static_uniform_n1curl_p5_h10_ny4` |
| mesh / element | `(6,4,14)` / uniform N1curl p5 |
| ICNTL(14) | requested=40，observed=40 |
| validation target | 未访问；package 中没有 `sealed_validation_indices.npy` |

训练包在 artifact 目录中只读保存。`TRAINING_DATASET_VERIFICATION.json` 是独立 checker 的重算结果；它逐行重读 Case124 formal/execution records，重算身份、Gate、数组 shape/dtype、order/mask 轴和文件 hash，结果为 `pass`。

24 个 blind 设计只作为 response-blind tuple 用于拓扑覆盖和互斥性检查。它们与 96 个 training tuple 无交集；blind response 仍为 0/24、未生成 package。
