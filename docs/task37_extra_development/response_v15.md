# Task037-extra Response V15：W18A-S1C 离线二维 span recovery

`response_v14.md` 保持冻结。本文件只记录 W18A-S1C 的一次 recovery offline diagnostic；没有新的 action、MPI、KSP、PDE、RTA 或文档覆盖旧证据。

## 先说结论

“离线二维 span”用通俗的话说，就是把已经保存的两条物理方向 `p1` 和 `p2` 当作两根固定的箭头，只在这两根箭头张成的二维范围里寻找最好的复数线性组合。它读取冻结残差和已保存物理像，直接计算最佳组合后的剩余比例；不会再次调用物理算子，也不会运行求解器。因此它只是这两条既有方向的组合上限检查，不代表其他新方向或未来方法不可能成功。

S1A 的 v1 首次运行在数值计算前就因 checker 内嵌 SHA 少一位而停止。它是 input-evidence failure，未进入数值、未决定 span lane；v1 原文件和原 classification `W18A_OFFLINE_SPAN_FAIL` 完整保留。修复 checker 后，S1C 只对同一冻结输入做一次 recovery。

S1C 的 authority Gate 全部通过，实际数值结果为：

| 项目 | repeat 1 | repeat 2 |
|---|---:|---:|
| direct span rho | `0.8732812469280545` | `0.8732812469280545` |
| energy rho | `0.8732812469280448` | `0.8732812469280448` |
| single-column rho | `0.8814092210776882 / 0.8918283239976346` | 相同 |
| solution/image norm | `1.4962119379374437 / 0.7807134026632232` | 相同 |

预声明 span Gate 为 `rho <= 0.85`，所以 S1C 是真实数值负结果：`0.8732812469280545 > 0.85`。它只关闭 W18 已保存 `p1/p2` 的二维 span lane，不是 PDE 失败。

## 可复核的二维计算

两次 repeat 的系数完全相同：

```text
c = [0.5993370638203415-0.422505007282305i,
     -0.3479971248183352+0.3174952090480066i]
```

```text
G = [[8.287408046061365,
      8.433761195521047+0.08592376617149038i],
     [8.433761195521047-0.08592376617149038i,
      8.748616651004214]]
h = [2.004745773458913-0.8536938466009105i,
     1.973869009746229-0.8371597605689928i]
singular_values = [0.2840097038250844, 4.117689058828843]
rank = 2
rank_threshold = 1.1703176195478712e-13
condition_number = 14.49840974928392
```

Hermitian defect 为 `0`，normal-equation closure 为 `5.1709203794237836e-17`，direct-vs-energy 差为 `9.769962616701378e-15`。两次 solution 与 physical image 的 relative differences 都为 `0`，exact identity 通过；所有组合 norm finite。

输出的 checks 中，`input_identity`、`repeat_identity`、`finite`、`gram_hermitian`、`rank`、`normal_closure`、`direct_residual_recompute`、`direct_energy_identity` 和 `single_rho_authority` 均为 `true`，只有 `span_rho=false`。输出 classification/status 为 `W18A_OFFLINE_SPAN_FAIL / gate_failed`，`span_lane_decided=true`，`close_w18a_nested_span_lane=true`，`qualified_for_bounded_followup=false`。整个过程 `action_run_count=0`、`ksp_call_count=0`、`pde_call_count=0`，`pde_pass=false`、`official_rta=false`。

## 身份、重复性和边界

- producer source：`839ce6733db2dc737f5c8bfb6347633f53161d82`
- checker source start/end：均为 clean `282a329d29b2819a64131607ef626cd611404d8b`
- 输入 W18A formal v2 file SHA：`3d9110cf7127333b676e96c5e7dd5cace23ecadc30127063d7f87171d510eb61`
- 输入 W18A formal v2 embedded evidence：`2132d54aacd70f38ea93e8c0886f7d2a5b86b8da6748d322edfc1d85afebc45f`
- 输入 raw summary SHA：`a82fb01c60b48575c2df59649375e3d330f85ba3edf43f1bd59c84bb2b29a4b5`
- 输入 watchdog summary SHA：`a32275d426cfe826f80be46dc8fbeba481e5bd8047589454f77b77b7c7a953eb`
- S1C v2 file SHA：`0b1418c1cb4e58173519b2e249a9a85f2f1674228fc49943119f7bc9019d5451`
- S1C v2 embedded evidence：`6da0b3c7e747b2ef7030d8e27196f659b8e12d13f9e35ab7b4d91d80ed9786bf`
- S1A v1 file SHA 保持：`7431ec84d2f5324c0fe9079a519e7c87196fd75d74d4ce40ccb04e8cd01601b0`
- W18A formal v1 SHA 保持：`0c86b687fd76f366bd9148fec734794fdf21b2a3d0bf300fc502981cb48c210f`

主结论是：这两条已保存物理方向的二维组合仍不能达到 `0.85`。因此不能把 S1C 写成 PDE 失败，也不能据此声称所有其他方向都不可能；只能关闭这个有限、明确的 W18A p1/p2 span lane。下一步不得盲目增加同一 nested auxiliary 的 outer steps。任何真正不同的机制都必须先经监督审核，明确有限 Gate，并先做资源 preflight。

full time-harmonic PDE、official field/RTA、direct-authority physics comparison 和最终 `<2,000,000,000 B` process-tree 测量仍为 `not_run`。

## 证据

- [S1C v2 record](../../benchmarks/cases/101_task37_extra_development/records/m6b_w18a_p1_p2_span_diagnostic_v2.json)
- [W18A formal v2](../../benchmarks/cases/101_task37_extra_development/records/m6b_w18a_839ce67_formal_resource_closeout_v2.json)
- [S1A v1 input-evidence record](../../benchmarks/cases/101_task37_extra_development/records/m6b_w18a_p1_p2_span_diagnostic_v1.json)
