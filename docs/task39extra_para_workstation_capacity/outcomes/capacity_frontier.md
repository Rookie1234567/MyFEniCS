# 当前能力与容量边界

| 对象 | 状态 | 可以得出的结论 |
|---|---|---|
| native R1 13.5 nm Si / p6h10 | 性能screen停止 | 32GiB小案例cap内完成p4 LU与62步；不能称复现通过 |
| native R1 matched reference | NATIVE_OWN_PASS_MATCHED_REFERENCE_WSL_ARRAYS_PARTIAL | 24GiB planning admission、80通道/功率/场比较通过；不称完整WSL全场复现 |
| R2 13.5 nm notch、匹配native reference | `GLOBAL_SWAP_ATTRIBUTION_UNRESOLVED`（attempt1清场） | 仅到iteration3；没有own资格、E/H、完整80复幅值或能量比较资格，5 nm保持锁定 |
| S5 W / p6h4 | NOT_RUN_BY_PREVIOUS_GATE | 没有本次短波计数、symbolic或numeric上界；不推测可算 |
| S3 W / p6h2.5、S2 W / p6h1.5、G | NOT_RUN_BY_PREVIOUS_GATE | 未运行，不把2TiB总容量当安全或精度证明 |

本轮没有native own-pass点、没有最短成功波长或最细成功网格。停止原因是原方法在当前执行实现下的首段耗时，不是内存容量、int32溢出、p4数值失败或物理Gate失败。旧WSL V5成功基线保留其历史资格，不能替代本机资格。

阶段资源与derived对象载荷见[复现报告](reproduction_13p5nm.md)。若获准对已验证的性能修复再作一次formal R1，仍必须从零、clean SHA、独立冷缓存、整树watchdog，遵守同一screen/solve/physical Gate；禁止从62步检查点warm-start。通过R1后才谈R2与条件匹配reference，再按原合同讨论短波。当前不开发新迭代法、子域法或替换预条件器。

## 最新门控位置（attempt3）

13.5 nm Si original 的本次 own solve 与 independent output gates 已通过，但 `BALANCED_OUTPUT_AUTHORITY_LIMITED` 和 `WSL_FULL_FIELD_COMPARISON_PARTIAL` 仍使完整 R1 关闭。见 [attempt3 compact](records/r1_attempt3.json)。R2 notch attempt1 已因全局 swap 归因未决受控清场，不能把两页全局 pswpout 解释成 OOM或数值失败；5 nm仍未解锁。

上述 native direct matched-reference 审计已完成并记录；R2 attempt1 的独立负结果待主控审核，暂不重跑、不进入匹配 reference 或5 nm，不新增 direct 算法、PC 或防御性框架。

本轮 5 nm 的材料身份按用户最新权威输入为 Si（`density=2.33`，`n=0.99396854453+0.00435380777i`，运行时 `epsilon=n*n`），不能沿用旧 W 标签宣传；实际 5 nm 仍待 13.5 nm original 与 notch 的完整资格。
