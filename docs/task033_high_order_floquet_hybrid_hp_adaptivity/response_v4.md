# 对 `review_report_v3.md` 的回复

## 总体处理

接受审阅结论：

```text
Phase B p3 = accepted
Phase B p4 = accepted with stated two-mode scope
Phase C p3/h5 = approved with candidate-specific C0
p3/h3, p4 target and adaptivity = not approved
```

本轮没有机械地把“五项最小矩阵”都强制运行。C0 对 full3D、M80、M120、M160 和
augmented anchor 分别判定；full3D 的独立 factor-payload 中心与保守上界失败，
因此按审阅合同记录 `not_run_by_memory_gate`。其余四个 Hybrid 候选各自安全，
按顺序实测并闭合了 Hybrid 组件。最终分类保持：

```text
hybrid_component_closed_full3d_not_run_by_memory_gate
whole_phaseC_pass = false
```

## 逐项回应

| 审阅要求 | 处理 | 结果 |
|---|---|---|
| 冻结新 clean source SHA | 数值实现先提交，运行绑定完整 SHA | `b636444b...` |
| source Gate 包含 nonignored untracked | watchdog 前后使用完整 `git status` | pass |
| 同一 numerical source | C0、三档 Schur、augmented 全部同一 SHA | pass |
| 刷新 limit/host/cgroup/swap | C0 现场读取，不沿用旧 Phase-0 常数 | effective 12.843 GiB，swap 0 |
| 候选级双中心预测 | 五个候选分别保存中心、上界和决定 | pass |
| full3D Gate 失败不得强跑 | 第二中心 15.031 GiB，上界 18.038 GiB | `not_run_by_memory_gate` |
| Schur-minimal M80/M120/M160 | 每次一个容器、MPI4、外部 watchdog | 三条 `measured_shard_pass` |
| M120→M160 截断证据 | R/T/A 与显著逐阶复幅均复算 | mandatory + strong pass |
| 条件 M240 | 只在 M120→M160 失败时运行 | 不需要，未运行 |
| 一个 augmented anchor | 在收敛的 M160 与 minimal 比较 | pass |
| no swap / memory authority | worker RSS、cgroup、swap 全记录 | pass |
| p3/h3、p4、adaptive | 未获批准 | 未运行 |

## 对 source reuse 边界的修正

`review_report_v2` 正确指出 Phase B 修改 trace 后不能笼统写“所有 numerical source
未变”。本轮将兼容性范围收窄为 `case090_pure3d_floquet_core`：

- Case090 evidence SHA `6613f94...` 必须是当前 SHA 的祖先；
- pure-3D Floquet core 不得有任何未批准改动；
- `modal_trace_projection.py` 明确记录为 Hybrid 数值组件改动，不再伪装成
  “全仓数值源码未变”；
- Case090 只作为高阶 core launch prerequisite，不作为当前 full3D reference；
- 目标 Hybrid 在 `b636444...` 上重新实测。

正式记录中的 reuse kind 为
`audited_case090_core_compatible_descendant`，disallowed changed paths 为空。

## C0 负决定

full3D 的两个中心为：

```text
effective p/h RSS center = 6.444557 GiB
assembled NNZ -> fill -> factor payload -> RSS center = 15.031264 GiB
conservative upper = 18.037517 GiB
live center limit = 10.549841 GiB
live upper limit = 11.742432 GiB
```

第二条链使用 Task029 p2 target h5/h3 的实测 RSS、assembled/factor NNZ 和
Case090 同网格 p2→p3 NNZ 比。两中心的分歧本身就是风险信号；不能选择较低者作为
启动许可。OOC、BLR 或 MPI2 的历史结果也没有形成已资格化、足以跨过当前 Gate 的
p3 full3D 方案。因此暂不修改审阅 Gate，也不通过 swap 或 OOM 后补写强跑。

## Hybrid 实测结果

| 路径 | memory authority | max-rank total | 状态 |
|---|---:|---:|---|
| Schur-minimal M80 | 2.278 GiB | 63.66 s | pass |
| Schur-minimal M120 | 2.492 GiB | 85.10 s | pass |
| Schur-minimal M160 | 2.641 GiB | 106.98 s | pass |
| augmented vs minimal M160 | 4.148 GiB | 114.05 s | pass |

M120→M160 的最大 R/T/A 绝对差为 `7.216e-14`，显著逐阶功率与复振幅相对差为
`3.676e-10` 与 `1.925e-10`。M160 的 true residual 为 `2.277e-12`，
`R/T/A=0.001090095685264 / 0.600622368221012 / 0.398287536093723`，
volume closure error 为 `1.874e-12`。bottom/top E 相对误差为
`1.913e-8 / 2.061e-8`，H 为 `6.914e-4 / 6.175e-4`。

augmented 相对 minimal 的 modal coefficient、bottom local field、top local field
误差为 `2.801e-13 / 1.680e-13 / 2.279e-13`，最大 R/T/A 差
`3.131e-14`；没有 dense interface square 或 full field/mode gather。

## 没有升级的结论

以下意见没有采纳为“通过”，原因不是保守措辞，而是证据确实缺失：

- **whole Phase C**：未通过；full3D 没有运行；
- **same-degree p3 Hybrid/full3D equivalence**：未证明；
- **selected-plane E/H against p3 full3D**：不可用；
- **p3/h3、p4 target、adaptive/buffer**：未获批准且未运行；
- **0.7 nm / 1 TiB**：没有新增 PDE 或可行性证明；
- **完整 Task033 formal manifest**：仍为 `NOT_RUN`。

Hybrid 漏斗与路径等价证据有独立价值，所以在候选安全时继续执行是合理扩展；但它们
不会被用来替代 full3D 缺口。

## 当前停止点与后续

本轮已完成审阅允许且资源 Gate 允许的全部工作。无需重复 M80/M120/M160，也无需
补跑 M240。若要继续关闭 whole Phase C，需要新的独立审阅先解决 full3D：

1. 批准更大有效内存预算，或资格化新的低内存 p3 full3D 路径；
2. 重新计算 candidate-specific C0，不手工覆盖旧 veto；
3. 在同一 clean SHA 上生成 p3/h5 full3D；
4. 补齐 R/T/A、显著逐阶、接口和 selected-plane E/H 的同阶对照；
5. 之后再决定是否批准 p3/h3，而不是直接进入 p4 或自适应。

详细数值与证据边界见
[`outcomes/p3_h5_phaseC.md`](outcomes/p3_h5_phaseC.md)；tracked 轻量摘要见
[`phaseC_summary.json`](../../benchmarks/cases/091_hybrid_hp_adaptivity_feasibility/records/stage3_p3_h5/phaseC_summary.json)。
