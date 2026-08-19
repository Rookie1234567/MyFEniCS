# V6 port/modal two-level side PC：bottom component 结项

## 结论

V6 的 port/modal two-level side PC 试图把困难的端口/模态方向交给一个很小的
Petrov–Galerkin 修正，把其余方向交给一次固定的 whole-endcap ILU(0)+DtN
Woodbury 基础动作。通俗地说，它希望用“便宜的普通修正 + 少量物理困难方向”替代
完整侧因子，从而降低峰值内存。

本次 bottom-only formal 在 full ephemeral packet ready 后超过冻结的 22 GiB
construction hard line，尚未创建 owner-row basis、rank-64 checkpoint 或任何 probe。
因此 V6 port/modal family 是真实的 resource-controlled negative；不进入 top、
both-side、outer、recovery 或 full formal。

| 项目 | 结果 | 分类 |
| --- | --- | --- |
| reviewed source | 52f34262232f9fd84d803a5f59fe5e4cb23acc6a | formal source |
| 物理配置 | 5 nm、1°、phi=0°、S、p6/h4、M480、MPI8 | frozen |
| bottom process-tree peak | 23,649,669,120 B = 22.025470733642578 GiB | measured |
| construction hard line | 23,622,320,128 B = 22 GiB | contract |
| overshoot | 27,348,992 B = 0.025470733642578 GiB | sampling/termination observation |
| swap | 0 B | pass |
| formal classification | bottom resource controlled stop | negative |
| exact-side full formal | forbidden；exact-side remains oracle only | not_run |

## 两次 attempt

| attempt | source / raw root | 实际发生 | 结论 |
| --- | --- | --- | --- |
| initial | aac7e33e7e29511f83a0a168b256145e323d5930 / results/task039_v6_h4_port_modal_bottom_component_mpi8_aac7e33e | right-only packet 使 ModalTraceProjection 读到空的 left_full，8 ranks 一致报 AttributeError；peak 21.419574737548828 GiB，checkpoint 未开始 | implementation failure，不是方法结果 |
| authoritative rerun | 52f34262232f9fd84d803a5f59fe5e4cb23acc6a / results/task039_v6_h4_port_modal_bottom_component_mpi8_52f34262 | full right/left packet transient hydration 后达到 fixed Woodbury ready；随后在 packet full-ephemeral ready 后触发 22 GiB hard stop | resource-controlled stop |

第一轮 raw 原样保留，不能与第二轮合并成数值失败。第二轮 exit_status=1、
result_classification=memory_terminate；POSIX process group SIGTERM 成功，5 秒内
退出，无需 SIGKILL。

## 已取得的 setup evidence

| marker / 对象 | measured evidence | 边界 |
| --- | --- | --- |
| bottom side system ready | global_F_materialized=false；没有新显式 component matrix；没有 packet arrays hydrate | bottom-only 接线成立 |
| fixed Woodbury ready | whole-endcap ILU0 + fixed DtN Woodbury；nested_ksp=false；exact/global direct factor=0/0 | base factor count=1，未到最终 cleanup |
| Woodbury state | auxiliary count=296；W=81,070,848 B；K rank=296；condition=10.470528383360438 | ready marker |
| packet full-ephemeral ready | 480 modes，right/left vectors hydrated，vectors_before_destroy=1920，qep_calls=0 | 最终 release marker 未到达 |
| last worker marker | v6_port_modal_bottom_packet_full_ephemeral_ready，worker elapsed 474.0589539189823 s | owner-ready 前停止 |

固定 Woodbury action 的数学身份仍是既有固定线性基础动作；本轮没有把它误报成
exact side factor，也没有接回 fixed-budget Krylov 或 nested KSP。

```math
M^{-1}=M_0^{-1}+Z E^{-1}Y^H(I-FM_0^{-1}),
\qquad E=Y^H F Z.
```

这里的 Z/Y、E、rank ladder 和 holdout numerical probes都没有正式生成。因而不能
报告 rank、condition、repeat、linearity、true residual 或 preferred residual 的
通过/失败值。

## Gate 重算

| Gate | authority | 结果 |
| --- | --- | --- |
| process-tree absolute resource | peak 22.025470733642578 GiB > 22 GiB | false |
| construction closed interval | 缺 construction_end；closed interval peak | not_available，不能写 measured interval pass |
| retained apply-state <=16 GiB | retained marker 未到 | not_available |
| numerical six-probe Gate | owner/rank64 未到 | not_run |
| exact/global direct factor | ready 时 0/0；最终 cleanup未到 | ready measured；final lifecycle not_available |
| packet/QEP release | qep_calls=0；最终 release Gate未到 | final not_available |
| top/both-side/outer/recovery/RTA/field | 未启动 | not_run |

全过程 peak 已足以裁决 resource Gate=false；construction interval 没有 end marker
这一事实不能被误写成 interval measured。layer graph 也没有 bottom_F_ready、
row-layer labels 或 pair-NNZ 结果，保持 not_available；sweeping prototype 未获授权。

## 证据入口与停止边界

- [compact record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v6_port_modal_bottom_component_v1.json)
- [V6-1 post-compaction setup](v6_post_compaction_exact_side_setup.md)
- [V6-1 layer graph audit](v6_side_layer_graph_audit.md)
- raw root（ignored）：results/task039_v6_h4_port_modal_bottom_component_mpi8_52f34262

此前 V6-1 exact-side setup 已以 42.70841979980469 GiB 超过 42.019652939 GiB
setup line，并关闭 exact-side full formal。此次 port/modal bottom component 又在
22 GiB construction line 失败，因此 V6 不再进入 top 或 full/two-side candidate。
不调参、不增加 rank、不重跑、不创建第三 family；ordinary defaults 和历史 V5
证据不改写。
