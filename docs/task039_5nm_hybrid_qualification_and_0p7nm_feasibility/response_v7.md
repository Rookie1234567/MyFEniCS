# Task039 Review V6 最终回应

## 1. 身份与范围

| 字段 | 值 |
| --- | --- |
| branch | codex/20260812-task39-5nm-hybrid-0p7nm-feasibility |
| base master | 438caf150439343ee7c4c58ad7e02a3da812a23c |
| reviewed formal source | 52f34262232f9fd84d803a5f59fe5e4cb23acc6a |
| final docs handoff SHA | 本文档提交前为 pending；由最终 Git 报告给出，不在本文自指 |
| formal input | 5 nm、1°、phi=0°、S、p6/h4、M480、MPI8 |
| ordinary defaults | unchanged |
| full pytest / CI | not_run |

本回应覆盖 V6-0、V6-1 和 V6 主 family 的实际边界。V6 整轮包含代码、focused
tests、正式 component 尝试和 controlled stop；本次最终 closeout turn 只写
compact evidence 与 docs，不改数值代码，也不新增 heavy。

## 2. V6 结论总表

| 阶段 | 实际结果 | 分类 |
| --- | --- | --- |
| inherited audit | V5 direct、iterative、compaction、streaming 和 exact spool 身份继承 | completed |
| V6-1 exact-side setup-only | peak 42.70841979980469 GiB > 42.019652939 GiB | controlled resource stop；exact-side oracle only |
| V6 layer graph | bottom_F_ready、row-layer map、pair NNZ、bandwidth 未取得 | not_available；sweeping not_authorized |
| V6 port/modal bottom component | peak 22.025470733642578 GiB > 22 GiB；swap 0 | authoritative resource negative |
| V6 owner-row Petrov basis | owner-ready/rank64 未到 | not_run |
| V6 six probes | numerical residual/repeat/linearity 未到 | not_run |
| V6 top/both-side/outer/recovery/RTA/field | 未启动 | not_run |
| 0.7 nm PDE / arbitrary-3D qualification | 未启动 | not_run |

因此当前没有通过 half-memory strategic target 的 h4 Hybrid iterative candidate。

## 3. 两次 V6 port/modal formal attempt

| attempt | source / peak | 发生了什么 | 裁决 |
| --- | --- | --- | --- |
| initial | aac7e33e；21.419574737548828 GiB | right-only packet hydration 删除了 ModalTraceProjection 所需的 left_full，8 ranks 一致报 None.getSize；checkpoint 未开始 | implementation failure，不是方法负结果 |
| authoritative rerun | 52f34262；23,649,669,120 B = 22.025470733642578 GiB | full right/left packet transient ready 后超过 23,622,320,128 B hard stop；SIGTERM 成功，无 SIGKILL | resource-controlled stop；family closed |

第二轮的 hard-line overshoot 为 27,348,992 B = 0.025470733642578 GiB。它来自
0.25 s 采样/终止时序，不是允许余量。compact record 中保留两次 attempt 的 raw
hash，完整 raw 不提交 Git。

## 4. 方法、生命周期与 Gate

Petrov–Galerkin side PC 的通俗含义是：先用固定、较便宜的基础动作处理大多数
方向，再用少量物理困难方向的左/右基做小矩阵修正。其计划公式为：

```math
M^{-1}=M_0^{-1}+Z E^{-1}Y^H(I-FM_0^{-1}),\qquad E=Y^H F Z.
```

本次 formal 只到 fixed Woodbury ready 和 full ephemeral packet ready，未创建 Z/Y、
E 或 rank ladder，因此以下字段必须保持未运行：

| 字段 | 状态 |
| --- | --- |
| base | measured ready；whole-endcap ILU(0)+296-aux DtN Woodbury；fixed linear；nested_ksp=false |
| base factor | ready 时 1；不是 exact side factor |
| exact/global direct factor | ready 时 0/0；final cleanup not_available |
| K / W | K rank 296、condition 10.470528383360438；W 81,070,848 B resident at ready |
| packet | full right/left transient hydration；vectors_before_destroy 1920；qep_calls 0 |
| owner-row basis / rank 64/128/256/512 | not_run |
| repeat/linearity/true residual | not_run |
| retained <=16 GiB | not_available；retained markers未到 |
| packet final release / factor final cleanup | not_available；不能写成0 |

construction closed interval 因没有 construction_end marker 为 not_available；不能
把它改写成 interval measured。全过程 authoritative process-tree peak 已超过 22 GiB，
所以 resource Gate=false。

## 5. V6-1 与 bottom resource 证据

| 证据 | peak | hard line | 作用 |
| --- | ---: | ---: | --- |
| V6-1 post-compaction setup | 42.70841979980469 GiB | 42.019652939 GiB | exact-side full formal 关闭 |
| V6 port/modal bottom | 22.025470733642578 GiB | 22 GiB | port/modal bottom family 关闭 |

这两个 hard stop 都是 simultaneous process-tree RSS authority，不是把对象 bytes
相加得到的数字。V6 port/modal raw 最后 marker 是
v6_port_modal_bottom_packet_full_ephemeral_ready（worker elapsed
474.0589539189823 s）；没有 outer-ready、final cleanup 或 numerical probe。

## 6. 继承 baseline 与容量边界

| baseline | measured evidence | 角色 |
| --- | ---: | --- |
| h4 Hybrid direct | 93.377006531 GiB | matched reference |
| V4 h4 exact-side iterative | 104.334560394 GiB | numerical/physics pass；resource regression |
| V5-2 setup-only | 85.376991272 GiB | setup baseline |
| h5 current direct sidecar | 50.356239318847656 GiB | nonblocking borderline；不是 continuum fit |

0.7 nm 只保留 conditional envelope：Full3D factor values-only 3234.18–32341.76 GiB
已经超过 2 TiB 的 90% line，但不是 formal；已知 air-side W+K/LU
205.049–208.878 GiB 约为 2 TiB 的 10.0%–10.2%，低于 70% line，却不能裁决
two-side total。V6 的 bottom construction resource stop说明 side factor-free路线也
必须在更早阶段取得真实资源证据；0.7 nm PDE仍 not_run。

## 7. 测试与证据检查

| 检查 | 结果 | 口径 |
| --- | --- | --- |
| compact JSON parse | pass | 新 V6 record |
| Markdown links / fenced math / table columns | pass | docs closeout |
| check_benchmarks --no-write | 302/302 pass | qualified activation fresh check |
| git diff --check | pass | docs/record-only |
| source-stage serial focused | 沿用 52f34262 evidence | 本 turn无 Python修改 |
| MPI2/MPI4 tiny | 沿用 52f34262 evidence | test235有一次 tmp cleanup warning；不声称 zero failures |
| Ruff / format / compileall | 沿用 52f34262 evidence | 本 turn无 Python修改 |
| full pytest / CI | not_run | 无 CI 声明 |

## 8. not_run、deferred 与 selective merge

| 项目 | 状态/建议 |
| --- | --- |
| top、both-side setup、outer、recovery、R/T/A、field | not_run；不得从 bottom stop 推断数值 |
| layer-aware sweeping | not_available / not_authorized |
| matrix-free channel modal | not_run |
| 0.7 nm PDE、Full3D new heavy、arbitrary-3D qualification | not_run |
| third BLR、generic budget/ILU scan、h5 rerun | forbidden/not_run |

| 分组 | 结论 |
| --- | --- |
| production-generic candidate | telemetry/marker alignment、hash-bound packet/spool catalog、collective lifecycle tests；仍需逐 hunk review，不改 solver default |
| research-only | factor-only exact handle、single-Schur/GMRES10 opt-in、streaming-W component、fixed-budget orchestration、port/modal Petrov source/runner和compact evidence |
| do-not-merge/promote | BLR campaigns、fixed-budget numerical-negative candidate、V6 bottom resource-negative candidate、未完成 top/outer/recovery、raw heavy artifacts |

最终结论：V6 没有建立“数值合格且低于 half-memory target”的 h4 Hybrid iterative。
exact-side 仅 oracle；port/modal bottom family因22 GiB construction Gate关闭；0.7 nm
capacity仍 unresolved/conditional。ordinary defaults、master 和既有历史负结果均未改写。
