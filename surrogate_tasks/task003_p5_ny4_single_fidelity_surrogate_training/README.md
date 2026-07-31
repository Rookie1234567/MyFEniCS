# Task003：p5/Ny4 单保真代理模型构建与资格化

## 状态

```text
status = ready_for_codex_execution
review_authority = Task002 review_report_v8.md
input_dataset = task002_m4e_p5_ny4_112_v3
training = 96
frozen_validation = 16
production_forward_model = S_PROD_FULL3D_STATIC_P5_H10_NY4
formal_angle_DOE = forbidden
formal_inversion = forbidden
```

## 目标

使用已经通过 Case119 资格化的 Ny4 compact dataset，建立一个可调用、带不确定度和物理约束的 S 偏振四维前向代理：

```text
(height_nm, width_x_nm, grazing_deg, azimuth_deg)
    -> aggregate R/T/A
    -> fixed-order outgoing S/P powers
    -> prediction uncertainty
    -> analytic power-carrying mask / domain status
```

复振幅代理作为本 Task 的条件式第二层目标；不得为了强行支持相位而降低功率代理的可信度。

## 开始前必须阅读

1. 根目录 `AGENTS.md`；
2. `surrogate_tasks/AGENTS.md`；
3. Task002 `review_report_v8.md`；
4. Task002 `response_v8.md`；
5. Task002 `outcomes/m4e_ny4_production.md`；
6. Task002 `outcomes/m4e_dataset_report.md`；
7. 本目录 `task.md`。

## 数据边界

Git 中只保存数据身份、hash、checker 和报告。实际数组位于生成电脑的 ignored artifact：

```text
benchmarks/artifacts/cases/119/m4e/compact_dataset/
```

Task003 第一阶段必须打包、计算 SHA256、转移到工作站并逐文件复核。不得假设 clone 远程分支即可得到 `.npy` 数据，也不得无理由重跑 112 个 FEM。

## 主要交付

```text
src/surrogate/
benchmarks/cases/120_task003_surrogate_training/
surrogate_tasks/task003_p5_ny4_single_fidelity_surrogate_training/
    outcomes/summary.md
    outcomes/test_summary.md
    outcomes/model_selection.md
    outcomes/frozen_validation.md
    response_v1.md
```

模型包必须绑定 dataset ID、dataset file hashes、训练代码 SHA、环境、seed、输出合同和验证指标。

## 停止边界

Task003 完成后停止等待 ChatGPT 审阅。不得自行开始正式 angle DOE、实验反演、MCMC、P incident surrogate 或前向 FEM 基线升级。
