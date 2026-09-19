# Task39extra Response V23：V22 original B 独立 profile 容量试验与证据收口

本批新增独立 `physical_p6_trace_p4_condensed_capacity_v22` profile，使用冻结有限额度完成一次实际 original B `Z3_ORIGINAL_H7P5` 试验，并完成 checker 最小字段修复。没有重新分解、没有重跑 PDE、没有提高额度、没有改写 raw evidence，也没有启动 A/C。

通俗地说，本次让稀疏直接解法实际建立 p4 因子，并测量这一步真实占用的内存。因子只是后续 p6 求解的准备；完成分解并不证明完整模型已经收敛。

## 第一屏结论

| 项目 | 结果 | 解释 |
|---|---|---|
| formal source | `57d1f601119900a52b7aa574fd4df557cfe0aa6c` | 这是实际 B 运行所绑定的 source |
| checker 修复 | commit `cf9f2346c400612e41926e0b21b7946e9a5e6715`；文件 SHA `3a4ab15fb39789689aa1d00cdaf21b51478d57b810fb78ec5fd3344426c52ce4` | checker source 与 formal run source 分开，不替换正式运行身份 |
| numeric | `INFOG(1)=0`，native numeric factor call completed | numeric 成功不等于完整 B solve 或物理通过 |
| actual factor entries | `INFOG(9)=INFOG(29)=221594144` | native actual factor-entry fields；与 p4 CSR `nz_used=32320342` 分开 |
| continuation | `RESOURCE_CONTROLLED_STOP` | allocated upper `4688000000 B` 超过 frozen continuation ceiling `3857054344 B` |
| RSS | watchdog tree RSS peak `6913208320 B`；numeric observer `6913241088 B` | 低于 8 GiB tree cap；RSS 不是停止原因 |
| backend | 非 MUMPS failure | `INFOG(1)=0`，没有 `-9/-19` |
| final science result | `official_result=false` | outer solve、residual、H6/p6/full field/physical output 未运行 |

停止是“冻结续算额度”门槛，而不是 RSS 超限或 MUMPS 失败。native `INFOG(19)=4687 MB`、`INFOG(22)=4326 MB`，used upper=`4327000000 B` 较 allocated 小，但不能绕过 allocated gate。旧 V11 预测为 `INFOG(16/17)=5060 MB`、request=`10131 MB`；V22 预测账与实测账分别保留：ICNTL23 frozen/request/readback=`4687 MB`，future inventory=`763172216 B`，future workspace peak=`1070871176 B`，inventory cap=`6442450944 B`，workspace pool=`1073741824 B`。

## 三层原始分类

三层状态不合并：

1. worker summary：`CONTROLLED_STOP / RESOURCE_CONTROLLED_STOP`；事件为 `v22_continuation_allocated_gate_failed`。
2. parent `run_summary.json`：`finished / WORKER_FAILED / exit_status=4`。
3. 独立 checker（修复后）：`CAPACITY_EVIDENCE_VALID_AUTHORITY_LIMITED`，`evidence_valid=true`，但 `full_numerical_pass=false`、`stage_pass=false`、`official_result=false`，physics=`UNKNOWN_CONTROLLED_RESOURCE_STOP`。

无 post-factor fresh hash：`matrix_identity_after_factor=null`、状态为 pending；不能用 before identity 冒充 after。A6、outer residual、完整 B physical field/80 ports、C 均 `not_run/unknown`。历史 A6/物理证据不被借用为本场 B 通过。

## 时间、资源与 JIT

- numeric factor phase：`217.1021214370012 s`。
- full workflow monotonic：`493.84353463599837 s`。
- V22 ledger elapsed：`538.0163161130178 s`。
- 旧 V21 predecessor ledger elapsed：`1884.4679552510706 s`；V21+V22 已知 ledger 累计=`2422.4842713640884 s`，只读单列，不是 monotonic 或全部历史总时间。正式 setup 已包含在 full workflow/ledger；只有运行外工程修复和 checker 时间独立且未实测，记为 unknown，不并入 PDE 时间。
- watchdog 1890 samples；descendants 已清场、remaining pids 为空、global swap delta=0、swap used=0。
- numeric observer 的 `inventory=1136131046 B` 是 callback 时尚未登记 factor 的账本值，不代表 numeric 后完整常驻库存；native allocated/used 另列，不混为同一口径。
- watchdog 顶层 stage 全部为 `workflow`；按现成 `worker_phase.phase` 和 `phase_started_clock.monotonic` 聚合，阶段为：`preflight` `4.546213274001275 s` / RSS `428781568 B`，`setup` `238.1087810299996 s` / RSS `3325509632 B`，`assembly` `28.39934371599884 s` / RSS `2377670656 B`，`factor` `217.8001403520011 s` / RSS `6913208320 B`，`cleanup` `4.046380408999539 s` / RSS `6880735232 B`。cleanup 的终点是 `watchdog/resources.jsonl` 最后一行的 `parent_clock.monotonic=12527.367271841`，包含进程退出清场；原始记录没有 `parent_end` 字段。`1886` 个样本有命名 phase，另 `4` 个 workflow 样本没有命名 phase。各阶段 PSS 与起点也在 compact 中保留，跨 UTC 跳变不参与时差计算。
- compiler 峰值只筛现有 `compiler_descendant_count>0` 的 `300` 个 watchdog 样本：setup RSS/PSS peak=`3325509632/3288349696 B`；这是该筛选口径，不是独立 compiler 进程全量峰值。

JIT 选择了 `v21_reuse_all_qualified`，但本场 11 个 FFCX compiler events 全部 `cache_hit=false`，0 hit、11 miss；事件 elapsed 之和=`101.78435976599758 s`，嵌套于全流程，不能与 total 相加。formal cache 有 60 个 hardlinked eligible files、source cache untouched。没有更细 cache-key miss 原因写入 raw evidence，因此本场实际编译成本如实保留，没有把“选择复用策略”写成“已命中”。

## Checker 初始问题与最小修复

初次 checker 输出曾报两个失败：`continuation_gate_recomputed`、`controlled_stop_classification`。初始 JSON 已被修正版覆盖，没有伪造原始快照或 hash。真实 producer 事件字段是：

```json
{
  "event": "v22_continuation_allocated_gate_failed",
  "facts": {
    "allocated_upper_bytes": 4688000000,
    "native_used_upper_bytes": 4327000000,
    "continuation_max_allocated_bytes": 3857054344
  }
}
```

checker 原先读取不存在的 `used_upper_bytes`；修复只改为读取真实 `native_used_upper_bytes`，仍独立由 native INFOG(19)/INFOG(22) 重算 allocated/used、比较 continuation limit，并保留资源与物理 Gate。worker、原始结果、额度和历史 ledger 均未改。

定向验证：`src/test/test_task39extra_v22_checker.py` 为 **6 passed**；真实保存 run checker 重跑 exit 0，capacity checks 全通过；compileall 与 `git diff --check` 通过。前期实现验证记录在 ignored `benchmarks/artifacts/task39extra/b_capacity_v22/root_engineering/luna_source_ready.md` 的 Verification，以及同目录 `supervisor_state.md` 的 Stage3 交接段：Stage3 **26 passed**、共享回归 **3 passed**、旧 A 只读默认 checker **65/65**。这些是不同用途的集合，不相加，也未因本次文档收口重复运行；全仓测试与 CI 未运行。没有扩展测试套件。

## 身份、历史与审阅边界

首次未带显式 `--v14-time-policy observe_only` 的入口校验已拒绝，未创建 attempt；随后按正式合同完成唯一 original-B attempt。正式 B run root、raw native/event/resource 文件、V22 ledger 和旧 V21 ledger 均保留。旧 V21 ledger SHA 为 `4448834859fd65e0ffe3d485b7d5d91a24d258e9970045daa28f90b88f10571f`，旧历史费用不清零、不覆写；无 A/C、无 replay、无自动重试。

本批最终文件：

- [V22 compact](outcomes/records/dual_condensed_capacity_v22_compact.json)
- [V22 decision](outcomes/records/dual_condensed_capacity_v22_decision.json)
- [tracked raw checker evidence](outcomes/records/dual_condensed_capacity_v22_checker.json)
- [V23 summary 增量](outcomes/summary_v23.md)
- ignored [result-ready report](../../benchmarks/artifacts/task39extra/b_capacity_v22/root_engineering/luna_b_result_ready.md)

定向 checker 测试和真实保存 run checker 结果见上述 tracked evidence；Ruff 不可用且未运行，无 CI 声明。最终状态：`AWAITING_CHATGPT_REVIEW`；`no merge`、`no new PDE`。旧 109 份文件、旧 profile、旧 ledger 保持不变。
