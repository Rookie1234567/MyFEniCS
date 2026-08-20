# Task039 Review V7 最终回应

## 1. 身份与范围

V7 整轮包含前述代码修改与 formal runs；当前最终 closeout turn 只做 docs/evidence，未修改 Python、未运行 PDE/heavy，也没有触碰 master。它不改写 `response_v7.md` 或任何 V6 负结果。

| 阶段 | source/evidence identity | 角色与状态 |
|---|---|---|
| Lane A setup-only | `f4073adabb91bffe5c3954b8ae8b63270efa3e15` | setup advancement authority；`81.056903839 GiB <=84.039305878 GiB` |
| Lane A full formal | `9e31ecf189081afcb8ca27b0374ec89af0094e2d` | 完整 5 nm formal；`80.025856018 GiB`，通过 |
| Lane B producer | `a33c19e7416460b11ceb61c2a7e32ab41fe1c1e7` | streamed basis component；通过 resource/lifecycle |
| Lane B consumer | `03aa96d88239c2d6997b6156e80200d25ef9b10d` | bottom component；numerical negative |
| Lane C graph raw | `95c20aad61414f3586651e960af9f20043462ef2` | graph-only run source；raw measured pattern |
| Lane C evidence checkpoint | `85efc8c1e4ba3a5d3ceaadee94bb3f541d75efaa` | closeout 前两份 compact/Markdown evidence 已提交并推送 |

`85ef...` 是本次 docs closeout 的 pre-closeout evidence checkpoint；最终 docs commit SHA 由批准后的 Git 最终报告给出，本文件不预写提交后的 HEAD。

### V7 阶段 commit 清单（不含本次 closeout）

| commit | 阶段职责 |
|---|---|
| `4ecd7666` | docs V7-0 audit |
| `f4073ada` | add exact-side setup-limit route |
| `ee0f4682` | record setup advancement evidence |
| `9e31ecf1` | add exact-side full-formal route |
| `c963be29` | record exact-side full-formal evidence |
| `98045a90` | add streamed owner-row Petrov core infrastructure |
| `4ee1a4be` | enable streamed Petrov source actions |
| `fb915a7a` | wire formal streamed bottom producer；首次 formal telemetry failure由其 root 保留 |
| `a33c19e7` | correct producer inventory telemetry / authoritative producer source |
| `19c042d1` | record producer evidence |
| `c13cba94` | add streamed bottom consumer；首次 formal ownership failure root |
| `03aa96d8` | remap streamed basis ownership / authoritative consumer source |
| `95c20aad` | record bottom consumer evidence |
| `85efc8c1` | record Lane C graph evidence |

这些是阶段 authority/证据边界，不把 implementation-failure run 改写成方法结果；本次最终 docs
closeout commit 尚未产生，故不在表中自指。

## 2. 统一结果与通俗解释

这里的“完整 workflow”包括 setup、求解、recovery 和物理检查；“component”只是一段可测流程。把 component RSS 直接当成 full workflow，会把尚未运行的对象和释放阶段漏掉。

| 结果 | 范围 | 峰值 RSS | 时间 | 结论 |
|---|---|---:|---:|---|
| matched h4 direct | full workflow reference | `93.377006531 GiB` | `7131.113596 s` worker_total | baseline / inherited authority |
| Lane A setup-only | setup component | `81.056903839 GiB` | `10649.634795 s` observed | advancement pass；不是 full Gate |
| Lane A exact-side full formal | full workflow | **`80.025856018 GiB`** | **`10126.232 s`** | 1 iter；physics/recovery/checker pass |
| Lane B streamed producer | component | `11.630760193 GiB` | `~415.6 s` | basis packet pass；无 holdout solve |
| Lane B streamed consumer | bottom component | `23.038208008 GiB` | `~632.8 s` | resource pass；rank512 numerical fail |
| Lane C graph-only | component | `not_measured` | `not_measured` | local-F pattern measured；无 solver |

Lane A full formal 相对 direct 节省 `13.351150513 GiB / 14.298113646%`，只达到 V7 `5_TO_20_PERCENT`。它是唯一一个同时完成完整 workflow、低于 direct 且通过数值/物理 Gate 的 V7 正结果；它没有达到 20%、30%、40%、50% 或 60% full-workflow saving 线。

这项 RSS 节省不是无代价的速度提升，但时间只能作 derived comparison：Lane A full formal 的
parent/observed elapsed `10126.231902 s` 相对 direct inherited `worker_total` `7131.113596 s`
增加 `2995.118306 s`、约 `42.0007%`。两者是 non-identical timing authorities，因此不是
strict performance qualification；outer 仍只有 1 iter，额外时间主要在两侧 factor 与 modal-Schur
setup。streamed bottom 因 rank512 numerical fail 没有 full wall/iteration tradeoff，不能外推其速度
或完整 workflow 成本。

| 目标 saving | full-workflow 峰值上限（GiB） | V7 状态 |
|---:|---:|---|
| direct / 0% | 93.377006531 | reference |
| 5% | 88.708156204 | reached by Lane A full |
| 20% | 74.701605225 | not reached |
| 30% | 65.363904572 | not reached |
| 40% | 56.026203919 | not reached |
| 50% | 46.688503266 | not reached |
| 60% | 37.350802612 | not reached |

## 3. Lane A：唯一完整 workflow 正结果

Lane A 使用 exact-side、single-build modal Schur 和 fixed outer GMRES10 setup；1 次 outer iteration 后 reported/global/bottom/top/modal residual 分别为 `3.506501655e-10`、`2.869197459e-10`、`1.732041001e-11`、`2.660035326e-10`、`5.776295397e-11`，均低于 `5e-9`。outer-ready RSS 为 `76.937850952 GiB`，swap 为 0；outer-ready factor 为 `1/1`，最终 cleanup 为 `0/0`，packet/QEP released，recovery、物理 checker、R/T/A、A_volume、closure、80/80 orders、12/12 powers 和 12/12 amplitudes 均通过。Full3D secondary 为 `not_available`，不是通过值。

setup-only advancement 的 `84.039305878 GiB` 来自独立的 f4073ada run；它不是 full formal 的 Gate。Lane A full formal 的正式资源比较是严格低于 matched direct `93.377006531 GiB`。

## 4. Lane B：producer 通过，consumer 数值关闭

Producer 在一个 packet 中保存 64/128/256/512 nested prefix，4 mmap 释放为 0，未打开 holdout/exact spool，不构造 base/factor/QEP/global basis；component peak `11.630760193 GiB`，约 `415.6 s`。

Consumer 先修复了 producer/consumer ownership remap；authoritative run 的 `23.038208008 GiB`、swap0、base ready1、exact/global0/0、nested KSP0、mmap/spool/finalizer release 均通过。这个 RSS 是同一 consumer process-tree 的共同 envelope，未按 rank 隔离。E=Y^H F Z 在四级均 full rank、condition 小于 `1e12`，但 worst mandatory residual 依次为 `219.375773963`、`310.531296720`、`1143.092533433`、`1521.816092530`，preferred maxima 依次为 `219.375773963`、`210.180979804`、`1143.092533433`、`1521.816092530`。因此分类为 `NUMERICAL_LIMIT_NOT_REACHED_BY_RANK512`，不是 resource/ownership/telemetry failure。

严格按 Review V7，top、both-side、outer、recovery、RTA 和 field exports 全部 `not_run`。没有一个可以称为“streamed Petrov full result”的结果。

## 5. Lane C：独立 graph-only 边界

Lane C 只做 bottom→destroy→top→destroy 的 action-side、explicit local-F CSR/static-condensation graph audit；没有 selected packet、QEP、factor、outer、recovery 或 PDE。bottom/top 都是 6 层、132300 rows、105038640 NNZ，其中 same-layer `75327840`、adjacent `29710800`、long-range `0`、block half-bandwidth `1`，并与 reference pattern 逐项匹配。wall/RSS/cleanup inventory 是 `not_measured`；约 16 分钟/~5.6 GiB 的 host 观察只作非正式备注，不能进入 Pareto。DtN global low-rank coupling 被排除在 local-F graph 外。

Lane C 只授权下一轮考虑 z-sweeping、hierarchical Schur 或 cyclic reduction；这些路线本轮没有实现、没有 heavy、没有可用性资格。

## 6. V6/V7 负结果与未运行项

| 证据 | 真实分类 |
|---|---|
| V5 BLR compressed-factor family | 两个冻结 profile resource fail；历史 raw/compact 保留 |
| V5 fixed-budget=32 | resource sample pass，但 modal true residual fail；没有 top/full |
| V6-1 exact-side setup | `42.70841979980469 GiB > 42.019652939 GiB`，exact-side full formal 关闭为 oracle-only |
| V6 port/modal | 首次 right-only 是 implementation failure；full-ephemeral 复核在 `22.025470733642578 GiB >22 GiB` controlled stop |
| Lane B first consumer | ownership implementation failure，保留 raw；不是方法结果 |
| V7 Lane B consumer | rank512 后 numerical source-family negative |
| 0.7 nm PDE / new Full3D | not_run |
| top/both-side/full Petrov after Lane B | not_run / forbidden by failed bottom Gate |
| full repository pytest / CI | not_run；无 CI 通过声明 |

## 7. selective merge 建议

| 组别 | 建议内容 | 边界 |
|---|---|---|
| production-generic（仍需逐 hunk review） | marker/telemetry alignment、hash-bound packet/spool catalog validation、collective lifecycle tests、已验证的 matrix-free C^H/D^H action | 不改变 ordinary/default solver；不把 case-specific evidence 当 production qualification |
| research-only | exact handle/factor-only、single-Schur/GMRES10 explicit opt-in、streaming-W component、fixed-budget/streamed orchestration 与 compact records | 仅显式 opt-in；保留 numerical/resource negative |
| do-not-promote | BLR campaign、fixed-budget numerical-negative candidate、V7 streamed Petrov numerical-negative candidate、未完成 top/outer/recovery、Lane C 尚未实现的 sweeping/hierarchical solver、raw heavy artifacts | 不合入 ordinary/default，不提升为 production |

ordinary defaults unchanged，master untouched。禁止项（第三 BLR、普通 ILU/budget scan、h5 rerun、0.7 nm PDE、Full3D 新 heavy、top/both/full Petrov 延伸）均未运行。

## 8. 测试与证据边界

本轮只做 compact/docs/evidence closeout，不运行 full pytest、PDE 或 heavy。Lane C focused graph tests 在 qualified activation 下 serial/MPI2/MPI4 均通过；代码阶段的 focused serial/MPI2/MPI4、Ruff、format、compileall 和 benchmark evidence 沿用各自 source SHA，不把它们写成本轮重新运行的全仓 CI。compact JSON、raw hash、Markdown links/table/fenced math、`check_benchmarks --no-write` 和 `git diff --check` 的最终状态以本轮命令报告为准。

历史负结果和首次 implementation failure 保持原样；raw results 仍是 ignored local artifacts，不进入 Git。
