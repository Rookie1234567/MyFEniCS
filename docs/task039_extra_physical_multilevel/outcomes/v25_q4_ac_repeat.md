# V25 Q4 AC 重复运行结果

这是用户额外授权的一个 Q4 original 性能重复，不是新的数值算法实验。它复用了原 Q4 的物理模型、p6/h7.5、粗阶 p4、MPI1/thread1 和 solver 参数；唯一的输入差异是独立 `run_id`。原 Q4 已通过结果不被本次结果覆盖。

## 结果

| 项目 | 本次重复 |
|---|---:|
| 状态 | `RESOURCE_CONTROLLED_STOP` |
| watchdog 分类 | `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED` |
| 退出码 | `-9` |
| 最后记录 outer iteration | 18 |
| 最后完整显式残差记录 | iteration 16 |
| iteration 16 显式真残差 | 0.0041437222964080065 |
| iteration 16 原始 `solve_seconds` | 356.40948556199953 s |
| iteration 32 | 无记录 |
| RSS/PSS 峰值 | 7314296832 / 7282536448 B |
| 作业树 VmSwap 峰值 | 0 B |

停止不是时间门触发：`observe_only` 时间门未超限。watchdog 观察到 WSL 全局 pswpout 从 7 增至 9，但无法证明这些页换出属于该作业，因此按安全策略清场。没有 final KSP、final native check、post-release residual、field 或 official output；不能把这次运行称为收敛失败或通过。

## 16 步对照

与前一个同配置 Q4 案例在同一 `iteration=16` 对齐：

| 记录 | 真残差 | `solve_seconds`（s） | 全进程树 RSS/PSS（B） |
|---|---:|---:|---:|
| 本次 AC 重复 | 0.0041437222964080065 | 356.40948556199953 | 7299502080 / 7267741696 |
| 前一 Q4 | 0.0041437222964080065 | 356.4489566070092 | 7290662912 / 7258555392 |

本次耗时少 0.03947104500967 s，残差一致。对应 p4 baseline（`pc=16`、`logical_call=1`）的 `native_A4_relative_residual` 两次均为 `9.12762008915742e-12`；本次/前一案例的 p4 elapsed 分别为 `0.8213633970008232 / 0.8465250529989135 s`。p4 原始记录没有独立内存字段，内存只能引用同节点全进程树样本。

## 证据入口

- [compact result](records/v25_q4_ac_repeat_result.json)
- [authorization record](records/v25_q4_ac_repeat_authorization.json)
- 原始 run summary：`results/euv_grazing1_phi0/task39extra_v25_q4_ac_repeat_original_h7p5__full3d_iterative__mpi1__Mna/20260922T014519.522186Z/run_summary.json`
- 原始残差：`results/euv_grazing1_phi0/task39extra_v25_q4_ac_repeat_original_h7p5__full3d_iterative__mpi1__Mna/20260922T014519.522186Z/monitor_residuals.jsonl`
- 原始 watchdog：`results/euv_grazing1_phi0/task39extra_v25_q4_ac_repeat_original_h7p5__full3d_iterative__mpi1__Mna/20260922T014519.522186Z/watchdog/resources.jsonl`
- 动态 checker：`results/euv_grazing1_phi0/task39extra_v25_q4_ac_repeat_original_h7p5__full3d_iterative__mpi1__Mna/20260922T014519.522186Z/v25q4_dynamic_checker.json`；因终态字段缺失为 partial `DYNAMIC_FAIL`，不作为 solver 失败判据。
