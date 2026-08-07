# Task037b 受控结项总览

## 一句话结论

H0 继承基线通过；H1 唯一一次 direct Hybrid MPI8 formal 在生成 Hybrid 解以前因近简并模态分组检查退出。它证明的是当前源码的 direct authority 尚未建立，不是 Hybrid 物理负结果，也不是 H1 residual 或 R/T/A Gate 失败。依停止规则，H2-H10 全部不运行。

## H0-H10 矩阵

| 阶段 | 状态 | 说明 |
|---|---|---|
| H0 | pass | 继承基线和文档治理完成 |
| H1 | failed_before_solve / controlled_stop | mode classification 的 inherited correctness regression |
| H2 | not_run_by_H1_gate | H1 停止规则 |
| H3 | not_run_by_H1_gate | H1 停止规则 |
| H4 | not_run_by_H1_gate | H1 停止规则 |
| H5 | not_run_by_H1_gate | H1 停止规则 |
| H6 | not_run_by_H1_gate | H1 停止规则 |
| H7 | not_run_by_H1_gate | H1 停止规则 |
| H8 | not_run_by_H1_gate | H1 停止规则 |
| H9 | not_run_by_H1_gate | H1 停止规则 |
| H10 | not_run_by_H1_gate | H1 停止规则 |

## H1 停止点

mode classification 发生在横截面 QEP 求解之后、Hybrid block system 生成之前。它把传播常数接近的模态分成小组，并建立后续界面方程需要的双基底。当前检查发现索引 50 和 52 属于不同组，但误差量达到冻结分组检查的边界，于是 fail closed。

| 字段 | 实际值 |
|---|---:|
| exception | NearDegenerateBlockPartitionSplitError |
| indices | [50, 52] |
| group_ids | [17, 18] |
| relative beta distance | 1.580086e-06 |
| identity row norm | 1.024637e-06 |
| identity max/cross-block max | 6.572908e-07 |
| limit | 1.000000e-06 |
| formal return code | 1 |

这一步没有产生当前 Hybrid 的解，因此不能填写为 0 的量都应标作 not_observed 或 not_run。

## 当前源码与 authority

| 项目 | 值 |
|---|---|
| branch | codex/20260807-task37b-hybrid-iterative-development |
| clean source SHA | 3f72ef3eb4f3002246802af30ef7bca6b0080888 |
| Full3D historical record | /home/Projects/MyFEniCS/benchmarks/artifacts/task035c_hybrid_channel_memory/p6_h10_full_static_mpi8_244b62e.json |
| Full3D record SHA256 | b8b428476cdeb4b80495f4a8b1c89e3bb2f67c682c695fc72bb59dbbbd94b4e3 |
| historical preflight authority SHA256 | 96ac3949efc236393d4c2dbc6e1fa334ad5ccb0e9796bdeba13fbe0515577dd8 |
| pinned source | 244b62e1fb4f299a468363cf90a2dd548dc34ff6 |
| pinned gate | pass |
| ordinary defaults | unchanged |
| H1 mode | explicit opt-in |

## H1 结果边界

| 结果组 | 状态 |
|---|---|
| H1 telemetry | not_observed |
| combined/bottom/top FE/modal residual | not_observed |
| interface E/H 与 middle-plane E/H | not_observed |
| powers/amplitudes | not_run |
| R/T/A 与 A_volume closure | not_run |
| rows/block shapes/matrix NNZ/factor NNZ | not_observed |
| official Hybrid result | not_run |

## 资源

| 指标 | 实测值 |
|---|---:|
| wall | 约 49.54 s |
| RSS/process-tree peak | 2647.4375 MiB |
| authority peak | 2.58538818359375 GiB |
| PSS peak | 1761.02734375 MiB |
| USS peak | 1637.375 MiB |
| swap | 0 |
| memory warning/termination/timeout | false / false / false |

该峰值来自 classification 阶段 whole-job，不是成功 Hybrid 求解的资源预测。

raw JSON 字段名虽含 max_*_mb，但本文按 bytes/1024^2 统一换算并显示为 MiB；authority 峰值显示为 GiB。

## 统一验收与未运行边界

| 能力/验收 | 状态 |
|---|---|
| current-source direct numerical authority | failed_before_solve |
| iterative Hybrid | not_run_by_H1_gate |
| exact action / exact LDU | not_run_by_H1_gate |
| bottom/top local inverse | not_run_by_H1_gate |
| one-sided / double funnels | not_run_by_H1_gate |
| MPI/restart | not_run_by_H1_gate |
| 12+12 powers/amplitudes、channel/field、RTA | not_run_by_H1_gate |
| merge recommendation | do_not_merge_to_master / wait for review |

## 测试与证据

测试和资源细节分别见 [测试汇总](test_summary.md)、[direct authority](direct_hybrid_authority.md)、[资源账本](resource_ledger.md) 和 [changed files](changed_files.md)。raw artifact 位于 Git ignored 目录；tracked docs 只保存相对路径和 SHA，不提交原始输出。

## 下一步边界

本轮不修 solver、不放宽 1e-6、不扫描 M、角度或 p-h，不进入 H2-H10。若要恢复 Task037b，下一份 review 只能先授权对历史 Case096 source SHA 244b62e 与当前 mode-classification 实现做窄差分审计，再决定是否允许一个最小实现修复和一个新的 H1 run。
