# Task040 结果摘要

Task040 的目标是研究：在保持冻结 Hybrid 方程、裸算子 F、物理输入和 M480 不变时，能否
用更低内存的 side inverse 替代两个完整 exact side factor。T40-3 只做底部、bare-F、
三组两层子域的传输机制 oracle；它不是完整 Hybrid 求解。

## 阶段总表

| 阶段 | 作用范围 | 状态 | 关键证据 |
|---|---|---|---|
| T40-0 | inherited audit | completed | branch/identity/ABI/基线已绑定 |
| T40-1/T40-2 | F/action identity、人工界面阻抗与 MPI tiny identity | completed | fixed `q=-i beta`、两界面 mass/support、bare F unchanged |
| T40-3 | bottom bare-F one-apply transmission oracle | controlled numerical negative | `TRANSMISSION_MECHANISM_FAIL`；worst rho `28.316064601533686` |
| V1-1 | fixed scalar transmission right-FGMRES screen | controlled numerical negative | `SCALAR_TRANSMISSION_DIRECTIONAL_FAIL`；all five r16 >= 0.9，32 not run |
| T40-4 | bounded patch core | not_run_by_gate | T40-3 mandatory rho failure |
| T40-5 | bottom scalable PC | not_run_by_gate | T40-3 mandatory rho failure |
| T40-6 | bottom inner FGMRES | not_run_by_gate | T40-3 mandatory rho failure |
| T40-7 | one-z-layer overlap fallback | not_run_by_gate | T40-3 mandatory rho failure |
| T40-8 | bottom full side | not_run_by_gate | Level-A prerequisite failed |
| T40-9 | top full side | not_run_by_gate | Level-A prerequisite failed |
| T40-10 | both-side setup | not_run_by_gate | Level-A prerequisite failed |
| T40-11 | full Hybrid | not_run_by_gate | Level-A prerequisite failed |
| T40-12 | conditional p6/h3 scaling | not_run_by_gate | Level-A prerequisite failed |

## T40-3 formal摘要

| 指标 | 值 |
|---|---:|
| modal+ rho | 16.512689191540417 |
| modal- rho | 14.24201480051629 |
| external rho | 22.945123935386228 |
| random0 rho | 28.316064601533686 |
| random1 rho | 25.70701839061571 |
| worst mandatory rho | 28.316064601533686 |
| peak RSS | 30,422,945,792 B = 28.333576202392578 GiB |
| wall | 660.6481867840048 s process sample |
| swap | 0 B |
| factors | cross-section 3 ready → 0 after cleanup; full-side/global/nested 0/0/0 |

所有实现身份、finite、zero-map、repeat、linearity、RP、mass/support 和 bare-F identity
通过；五个非零源的 rho 使正式数值 Gate 失败。physical source 只有独立 zero-map，不能
把它当作非零 transmission 证据。

exact subdomain solve 仍有 rho>1，说明当前缺失类别是人工截面上的跨截面/多模切向传播
耦合信息；固定标量一阶 impedance 不足以表达它。这不是把某个未运行的 coarse 或 modal
DtN 方案预先判为必需。

## 与继承 baseline 的资源边界

| 路线 | process-tree peak GiB | 口径 |
|---|---:|---|
| direct full workflow | 93.377006531 | inherited full workflow |
| exact-side iterative full workflow | 80.025856018 | inherited full workflow |
| T40-3 Level-A component | 28.333576202392578 | component only，不是 workflow |

T40-3 component 不能声明 saving tier，也没有建立 cold/reuse/full workflow peak、bounded
local patch capacity 或 h4→h3 scaling。不能据此判断 coarse information 是否必需，更不能
推出完整 Hybrid 或 0.7 nm 不可行。

## 选择性复用边界

| 类别 | 内容 | 结论 |
|---|---|---|
| reusable candidate | package-invocation watchdog 修复、interface support/mass 审计、factor owner cleanup 合同 | 可单独审阅，未改变 ordinary defaults |
| research-only | 三个 cross-section exact oracle factor、固定一阶 impedance、T40-3 负证据 | 保留证据，不作为 scalable PC |
| do-not-promote | T40-3 action 作为 side inverse、full Hybrid、0.7 nm capacity claim | 禁止提升 |

完整 raw 和日志留在 ignored results；轻量证据见
[compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_level_a_bare_f_transmission_v1.json)。


## V1-1 scalar Krylov screen

V1-1 formal completed on the frozen MPI8 component. The independent checker classified the five-source scalar screen as SCALAR_TRANSMISSION_DIRECTIONAL_FAIL; all five r16 values remained at least 0.9, so conditional 32 was not run.

Peak was 27.790115356445312 GiB, wall was 669.4473022361053 s, and swap was 0. This is a component peak, not a full-workflow saving tier. The V1-2 mode-aware/interface-Schur route is planned but has not run.
