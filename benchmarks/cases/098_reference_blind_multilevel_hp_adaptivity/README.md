# Case098：Task035e closed historical research index

## 状态

```text
case_role = closed_historical_research_index
production_benchmark = false
task_classification = PARTIAL_WITH_CONTROLLED_NEGATIVES_CLOSED
reference_certification = pass
true_local_h_local_p_capability = pass
automatic_reference_blind_hp_cycle = incomplete
direct_selective_trace = closed_controlled_negative
production_candidate = none
hybrid = not_run
iterative = not_run
ordinary_default = unchanged
```

Case098 只索引 Task035e 已冻结的研究证据。它不是 ordinary solver 的
production benchmark，也不能用于宣称自动 h/p 自适应已经成功。master 的
documentation-only integration 不包含本 case 的 workers、controller、schema、
records、plans 或 ignored artifacts；完整研究材料固定在
[`27ca26718b9ee60215243bcc98ffafcd46bfd221`](https://github.com/Rookie1234567/MyFEniCS/tree/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity)
及 Task035e 研究分支的后续纯文档提交中。

最终审阅 authority 是
[Task035e Review V1](../../../docs/task035e_reference_blind_multilevel_hp_adaptivity/review_report_v1.md)。

## 已通过的边界

| 项目 | authority result | 能说明什么 |
|---|---|---|
| p6/h10、p6/h7.5、p6/h5 reference | 三点均 59/59；pairwise 59/59 | reference certification pass；不是低内存 production 配置 |
| Path A current | 160 leaves；59,264 DoF；20,202 rows；8.17 GiB | cycle-0 stage pass |
| Path A full p-shadow | 160 leaves；62,284 DoF；20,564 rows；8.15 GiB | p component 与 global endpoint DWR pass |
| Path A full h-shadow | 181 leaves；level 0/1/2；66,434 DoF；10.237 GiB | true multilevel local-h、2:1、periodic/hanging 与 MPI8 pass |
| local-p/local-h active space | p4/p5/p6 inactive modes 不进入 rows/NNZ/factor | component capability pass |

这些结果没有产生 accepted transition，因此 `cycle_advanced=false`。

## 保留的 controlled negatives

| evidence lane | measured result | frozen decision |
|---|---|---|
| four-cell selected-p | 19/59 factor-two-or-neutral；25/59 opposite-sign | reject；cycle-0 current retained |
| single-cell p-up | 0/59 factor-two-or-neutral；30/59 opposite-sign | reject；cellwise-p quantitative predictor closed |
| post-action audit | single-cell remaining estimator +0.144216%；four-cell endpoint distance +47.7963% | cellwise partition 只可作 ranking/diagnostic |
| broad-p C2/P3 | E2 分别恶化 9.219512% / 9.227268% | broad-p lane negative |
| isotropic-h H2/H3 | E2 仅改善 0.021457% / 0.022178%，资源显著增加 | 合法但低效率的 h-lane negative |
| 160-leaf global p6 | 4/59；12.335 GiB | 精度正信号但资源失败；该 topology 关闭 |
| 160-leaf p5-trace/p6-interior | 0/59；8.999 GiB | mechanism diagnostic，不是 candidate |
| H10 M1 p5-trace/p6-interior | 52/59；低于 11 GiB | 低内存基础模型，精度不足 |
| projection-selected 200 face orbits | 50/59；13.004326 GiB | accuracy + resource controlled negative；projection ranking 关闭 |
| goal-DWR-selected 16 face orbits | 49/59；10.929794 GiB；zero swap | 资源通过、完整 59-goal 失败；direct selective-trace 关闭 |
| Path B v27 | current/p-shadow pass；h-shadow 11.055027 GiB controlled stop | partial only；不是 cycle 完成 |

最终 16-orbit 模型对显式优化的 6 个独立物理目标全部预测正确并恢复为通过，
但造成 10 个原已通过的旁路目标越界。它验证了局部 signed DWR 机制，却没有
通过完整多目标合同，不能提升为 production。

## 历史证据入口

以下链接固定到审阅数值快照，避免 master 文档指向未合入的相对文件：

- [cycle-0 v28 resource gate](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/path_a_cycle0_v28_resource_gate.md)
- [four-cell selected-p actual](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/path_a_cycle0_selected_p_actual.md)
- [single-cell p-up actual](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/path_a_cycle0_single_cell_p_actual.md)
- [post-action global-estimator audit](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/post_action_global_estimator_audit.md)
- [broad-p / isotropic-h sprint](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/fast_hp_sprint_v2.md)
- [mechanism-isolation sprint](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/mechanism_isolation_sprint_v1.md)
- [structured anchor and projection trace](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/structured_anchor_selective_trace_v1.md)
- [goal-oriented selective trace](https://github.com/Rookie1234567/MyFEniCS/blob/27ca26718b9ee60215243bcc98ffafcd46bfd221/docs/task035e_reference_blind_multilevel_hp_adaptivity/outcomes/goal_oriented_selective_trace_v1.md)
- [Case098 compact records at reviewed head](https://github.com/Rookie1234567/MyFEniCS/tree/27ca26718b9ee60215243bcc98ffafcd46bfd221/benchmarks/cases/098_reference_blind_multilevel_hp_adaptivity/records)

其中 sealed 47 MB hidden package、fields、matrices、factors、timelines 和 ignored
raw artifacts 从未因文档收口进入 master。

## 冻结的未运行项

```text
accepted selected-h = not_run
cycle 1 = not_run
Path B completion = not_run
hidden final audit = not_run
Hybrid = not_run
iterative = not_run
second selective-trace batch = not_run
threshold/ranking retune = not_run
```

下一条项目路线由项目路线文档固定为：

```text
static-condensed Full3D iterative
→ Hybrid direct 59-goal qualification
→ static-condensed Hybrid iterative
```
