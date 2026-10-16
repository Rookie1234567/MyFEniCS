# D13 已保存场与稀疏截断历史索引

本索引把先前保存的 D13 取证版本与当前 Task40 生产接线分开，便于审查时追溯失败、作废字段和更正。它不改变任何历史结论、阈值、数组或哈希，也不把诊断结果提升为求解资格。

## 历史文件归档

- 按旧启动 package `tmp/task40_d13_y2_scale_homogeneous_launch_v1/package.json` 的 `source.preserved_untracked_paths` 原样归档 72 个文件，共 1,377,255 字节；该 package 归档前 SHA256 为 `f9880a717ebce0bcf8fac2b58f57482efa4b4af44ae3464934fa73a71b20e27a`。文件未移动、删除或改写，历史记录中已有的 SHA256 值保持原样。
- 这些路径包含旧合约、sidecar、启动/接管/终态记录、校正记录、响应说明、诊断 worker/supervisor 和五个历史 pure/interface 测试。各版本仍以各自绑定的 source/worker/contract 身份为准；不能把旧包当作当前启动包。

## 失败、废弃与更正

| 记录 | 历史状态 | 使用边界 |
|---|---|---|
| saved-field action-only v1/v2 | 已被后续版本取代 | 保留以还原版本演进；不作为当前执行合同。 |
| action-only v3 | 启动/API失败，不是数值门结果 | VTU 与 E 场已读入，Basix 因复数元素 dtype 拒绝 DG6 构造；未创建 DG 空间、未重构 N1E、未建 carrier。原终态 SHA256 `e6eba69a865801257a74734e1a5d9fb17bf970c0341a2121532faf2b8750df6d` 保留。更正 receipt `d13_saved_field_port_action_only_terminal_correction_v3.json` SHA256 `abf8cf93d358436964106c30ccf0bb8797464edcb4e644fee992ed97ec62ef26` 说明了实际失败位置。 |
| action-only V4 | `FAIL/OPEN`，未获得 carrier 比较资格 | Y2/Y3 都因 `maximum_facet_unaveraged_tangential_trace_relative` 超过 `1e-10` 而拒绝 carrier 比较；终态 SHA256 `51713db449364f65bd3c714efcc4e3c578f5a57026b965615f2d3129ab1cf164`。 |
| action-only V5 | `FAIL/OPEN`，仍是诊断而非资格 | Y2 最大 facet 相对量 `3.134531344792558e-4`，Y3 为 `1.348820533203681e-4`，均高于诊断限值 `1e-10`；两案为 `NO_CARRIER_COMPARISON`。终态 SHA256 `7285e6d58f4c6b4e815dd043c3c5a5b8197f48b772ec9d455218c17eb0f1fe27`。此失败保留，不因之后的投影诊断改写。 |
| scale-homogeneous cutoff candidate v1/v2 | 已保存场诊断，不是 production/full-solve 资格 | v1/v2 保留各自合同与输出身份；production 默认仍为旧策略，Task40 新 profile 才显式选择相对阈值策略。 |

## 混单位字段与更正

早期字段 `merged_cut_boundary_vs_saved_total_aux_*` 将合并截断后的 boundary 值与未乘边界相位的 raw saved auxiliary 系数直接比较，单位不一致；这些字段不能用于误差结论或复用为通过证据，原文件不改。更正后的同单位比较先将 saved total auxiliary 系数乘实际边界相位 `P`，再与 candidate、untruncated 的 boundary 投影比较；raw coefficient、boundary total、incident 与 outgoing boundary amplitude 分别保留。更正说明见 `response_scale_homogeneous_cutoff_candidate_v2.md`（SHA256 `189f90506812776cc118d675745777c2937c7a4029bc54d43c26a971064d07a0`）及 validation receipt `d13_saved_field_scale_homogeneous_cutoff_validation_v2.json`（SHA256 `e8bc4aad951d27617f3d77f40c582678aff08565e64485bca38a6e3f945f4dcc`）。相应候选只支持保存场投影差异的局部解释，不证明旧 PDE 场或 carrier 合格。

## 当前生产证据范围

代码修正提交 `3ddee5b9a967f38a96dfee17734509c4161f4ed4` 修正 Task40 直接解的预释放证据布局：`evaluate_native_residual.retained_alpha` 是增广解的端口/modal 尾块，不是 trace 前缀；证据现在分别保存 `augmented_trace_solution` 与 `retained_modal_alpha`，并验证 native fact 与 modal slice 逐元素相等。报告同时绑定原有 `port_residual_relative` 与 `port_operation_scale` 的来源标量。

六键 full-primal witness 继续保留 audit 的 raw 投影字段，并额外记录每个模式的边界相位 `P`、归一化 `H`、total/outgoing 乘 `P` 后的复值及同单位差。`direct_projection * H` 只标为派生分子，不冒称独立积分；legacy projection audit 仍为观察项，不新增 solver gate。该证据在下一次完整 Y2 计算中、factor/matrix 释放前生成；本索引编写时尚未 fresh 或运行 FE，故不能声称这些新字段已有实测数值。

## 定向测试记录

- 当前 Task40 runner/policy/output 定向回归：29 passed；Ruff、compileall、`git diff --check` 通过，无 FE。
- 指定五个历史测试模块可收集，共 56 项；52 passed。其余 4 项是旧 worker SHA 或 frozen source HEAD 的身份断言与当前 source 不匹配（包括旧 action supervisor 的 worker hash、旧 v4 contract 的 HEAD，以及 v1/v2 candidate 对过期 HEAD 的错误优先级预期）。历史源文件按原字节归档，不改合同、不伪造旧 HEAD，也不把这些失败重述为数值失败。
