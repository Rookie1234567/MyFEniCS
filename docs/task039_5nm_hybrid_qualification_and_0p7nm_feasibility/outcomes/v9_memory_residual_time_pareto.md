# V9：内存—残差—时间 Pareto

这张表把完整 workflow 和 component 研究点分开。完整 workflow 必须同时有解算、残差、
recovery/physics 和完整生命周期；component 只说明某一段构造或 action 的资源，不可把较低
RSS 直接宣称为完整任务节省。

| 路线 / 方法 | 口径 | peak RSS | 时间 | 数值结果 | 资源/生命周期 |
|---|---|---:|---:|---|---|
| matched h4 direct | 完整 workflow baseline | `93.377006531 GiB` | `7131.113596 s` worker_total | inherited authority | baseline |
| V7 Lane A exact-side full | 完整 workflow | `80.025856018 GiB` | `10126.231902 s` observed parent elapsed | 1 outer iteration，physics/recovery pass | swap0；唯一完整低于 direct 的正式正结果 |
| V9-1 J1 | bottom component | `23.8684272766 GiB` | setup `78.705259702` + holdout `7.447137749` + apply `4.981149436 s` | worst `r_F=50.7689715097`，`r_A=50.2410648372` | construction pass；retained not_run |
| V9-1 F1 | bottom component | `22.1353225708 GiB` | setup `86.680200840` + holdout `7.970189338` + apply `5.368767116 s` | worst `r_F=367.2128685567`，`r_A=141.0763808200` | construction pass；retained not_run |
| V9-2 SN2-J | bottom component | `22.812664031982422 GiB` | `6.183576241 s` method marker interval；全程 `473.941922 s` | 5 mandatory 全 nonfinite；无 preferred | construction pass；retained not_run；factors3→0 |
| V9-2 SN2-SGS | bottom component | 同一 process envelope `22.812664031982422 GiB` | `23.778006799 s` method marker interval；非独立 RSS | 5 mandatory 全 nonfinite；无 preferred | construction pass；retained not_run；factors3→0 |

V9-2 的 `22.812664031982422 GiB <=45 GiB` 是 parent construction/overall measured
component 结果；retained 区间没有运行，因此不写 `<=30 GiB` pass。SN2-J 与 SN2-SGS 在同一
consumer process 中顺序执行，不能把它们的共同峰值拆成两个独立 RSS。

V9-1 和 V9-2 的低 component RSS 没有形成 full-workflow saving tier。当前完整 workflow
的最佳结果仍是 V7 Lane A 的 `80.025856018 GiB`，相对 direct 节省 `14.298113646%`；V9
没有产生新的完整 workflow。

## 统一的数值边界

V9-1 的 single-layer `J1/F1` 已记录 bare-F 与 full-side 两套 residual；V9-2 的两层
supernode 只允许记录 bare-F `r_F`，因为它们在 action 输出阶段已非有限。五个 mandatory
label 为 positive、negative、external、random773、random779；physical zero 只作
degenerate。SN2 两个候选都不能进入 V9-3。

相关证据：[V9-1 outcome](v9_bare_f_vs_full_side.md)、[V9-2 outcome](v9_supernode_side_preconditioner.md)、
[V9-2 compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v9_supernode_side_preconditioner_v1.json)。
