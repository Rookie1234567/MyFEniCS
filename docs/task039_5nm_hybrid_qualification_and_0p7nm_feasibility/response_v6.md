# Task039 Review V5 response

## 身份与范围

V5 整轮包含代码、组件和正式运行阶段；本次最终收口 turn 只读取既有 raw 并写 docs/compact evidence，没有修改数值代码，也没有在本 turn 新运行 PDE/MPI/QEP/heavy。full repository pytest 为 `not_run`。工作树状态由提交前检查单独记录；本页不把文档工作树状态冒充 formal-run preflight。

| 身份字段 | 值 | 说明 |
| --- | --- | --- |
| Task39 base master | `438caf150439343ee7c4c58ad7e02a3da812a23c` | V5 分支的 base |
| V5 reviewed head | `508d81ab1cffe26aff29038ab15f0b14a7516cde` | Review V5 审阅身份 |
| formal fixed-budget code | `ff89f07bc26aecbab6f60f06408c3ab364e9c5f4` | 本轮 fixed-budget raw 的源码 SHA |
| final docs handoff | `provided after commit` | response 不能自指未来 commit；由最终 Git 报告给出 |

V5 的目的，是先测真实常驻内存峰值，再判断是否值得优化。这样可以区分“某个对象理论上变小”与“整个进程树真的少用内存”，避免把数组 bytes 或单 rank 清理样本误报成系统节省。

## 统一结果

| 方法/阶段 | 数值与物理 | RSS / 生命周期 | 分类 |
| --- | --- | --- | --- |
| h4 Hybrid direct | own Gate pass，含 residual、projection、traction、R/T/A、canonical、external identity | `93.377006531 GiB` matched reference | `HYBRID_DIRECT_H4_OWN_PASS` |
| V4 h4 exact-side iterative | 1 iteration；五残差 `5.1673119e-10`、`5.1673072e-10`、`3.2985246e-10`、`4.7629854e-10`、`2.5758782e-10`；recovery/physics/direct comparison pass | `104.334560394 GiB` | `HYBRID_ITERATIVE_H4_EXACT_SIDE_NUMERICAL_PHYSICS_PASS_RESOURCE_FAIL` |
| V5-2 setup-only | 15-marker setup evidence，factor/object attribution | `85.376991272 GiB`；advancement line `84.039305878 GiB` 未满足 | setup baseline only |
| V5-3/4/5 | factor-only、single Schur、fixed GMRES、streaming-W component evidence | object bytes/组件 ru_maxrss 不替代 fresh h4 process-tree RSS | research-only evidence |
| BLR 1e-5 / 1e-3 | 数值 Gate 未建立 | bottom resource `75.89627456665039` / `95.39834594726562 GiB`，limit `59.7638938904 GiB` | `resource_fail`, family closed |
| fixed-budget32 bottom | modal traction residual `0.748109402736452` / `0.737754681505050`，limit `0.01` | setup interval `21.677326202393 GiB`；overall partial `21.700809478760 GiB`；无 numerical upper bound | `TASK039_V5_FIXED_BUDGET_SIDE_KRYLOV_NUMERICAL_NEGATIVE_CONTROLLED_STOP` |
| V5-S h5 current direct sidecar | main true residual `8.826952439936801e-10`，physical field/conormal pass；condensed full-operator `1.0501690969564719e-9` 超 `1e-9` | producer `1111.204334 s`；consumer-only `2636.955775 s`；serial cold `3748.160109 s`；RSS `50.356239318847656 GiB`；h5→h4 ratio `1.854328436631525` | nonblocking borderline controlled-negative |

## Fixed-budget raw 边界

fixed-budget raw 为 [record](../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v5_fixed_budget_side_krylov_component_v1.json)，root 为 `results/task039_v5_h4_fixed_budget32_bottom_sideonly_component_mpi8_ff89f07b`。它保留 `status=launching`、`exit_status=null` 和 `ledger=in_progress`；进程树已经清空，但没有 final cleanup marker。故 factor-after-destroy、action destroy、cleanup count 都是 `not_available`，不能写成 0。

physical RHS 是唯一 `degenerate_uninformative=true` 的探针；它的 0 residual/repeat 只作信息记录。modal traction 正负两条 mandatory probe 都是 finite，但 true residual 远大于 `1e-2`，所以没有继续 external/random、top、outer、recovery 或 R/T/A。setup resource sample 虽然低于阈值，却不能抵消 numerical Gate 失败。

## V5 阶段与职责

| 阶段 | 主要职责 | 证据身份 |
| --- | --- | --- |
| V5-0 / V5-1 | inherited baseline、h4 raw inventory 与 memory attribution | 对应 audit/attribution compact records；不重写 V4 raw |
| V5-S | h5 current-lifecycle direct sidecar，producer/consumer ownership 与生命周期 | `50.356239318847656 GiB` consumer；nonblocking borderline |
| V5-2 | h4 exact-side setup-only marker、对象 ledger、stage-aligned RSS | source `2ba0c44...`，setup peak `85.376991272 GiB` |
| V5-3 | factor-only MUMPS handle、F/C/H release 与 ordinary default regression | `61d3b06f38eea3131d3e5f7a7b82577ace5a9f1f` |
| V5-4 | single modal Schur、固定 sampled repeat、显式 GMRES10；默认 FGMRES90 保持 | `2eab55d70e4bd4f7473c908c88dcfa18e1c94e9b` |
| V5-5 | retained-W/streaming-W component与batch8选择 | `76d374f89452623ed59b525d3a24c0a7348c7d57` evidence runner |
| V5-7 BLR | 两个且仅两个冻结 compressed-factor profile；均 resource negative | formal sources `2f1e6581...` 与 `7e5d9b57...` |
| V5-7 fixed budget | 唯一 budget32 bottom-first side Krylov；数值 Gate 失败即停 | formal source `ff89f07bc26aecbab6f60f06408c3ab364e9c5f4` |

## V5-2 marker-aligned RSS 归因

这些是 V5-2 `memory_stages` 与 process-tree samples 对齐的观测点，不是每阶段最大值；对象 bytes、单 rank cleanup RSS 与 process-tree RSS 不相加。

| marker boundary | process-tree RSS (GiB) | 口径 |
| --- | ---: | --- |
| bottom F ready | `77.0812` | marker-aligned sample |
| bottom factor ready | `85.3308` | marker-aligned sample |
| bottom Woodbury ready | `79.8107` | marker-aligned sample |
| bottom construction cleanup | `48.4827` | marker-aligned sample |
| top F ready | `53.7873` | marker-aligned sample |
| top factor ready | `83.7078` | marker-aligned sample |
| top Woodbury ready | `83.7152` | marker-aligned sample |
| top cleanup / both actions | `79.6327` | marker-aligned sample |
| modal Schur ready | `80.5443` | marker-aligned sample |
| outer KSP setup ready | `71.8689` | setup-only；未进入 outer solve |
| all setup objects cleanup | `16.0022` | marker-aligned final cleanup |

V5-2 全程 peak 仍是独立的 `85.376991272 GiB`；上表不把任何单个对象容量解释为 peak 原因。

### V5-2 生命周期边界对照

下表只表达 marker 前后已记录的生命周期边界，不把 RSS 差值归因于某一个对象；对象 bytes 也不与 RSS 相加。V5-2 formal baseline 是 retained-W 路径，不能把它改写成 streaming-C evidence。

| 边界 | marker-aligned RSS | 已有证据支持的对象语义 |
| --- | ---: | --- |
| bottom Woodbury ready → construction cleanup | `79.8107 → 48.4827 GiB` | 保留 bottom factor、W、K/LU、action 所需状态；释放 construction-only F/H 等；C 按 retained baseline 处理，不宣称 streaming ownership |
| top Woodbury ready → cleanup / both actions | `83.7152 → 79.6327 GiB` | top construction cleanup 边界已记录；对象级逐项释放与 RSS 差额不可独立归因 |
| modal Schur ready → outer KSP setup ready | `80.5443 → 71.8689 GiB` | 仅能写 raw 证明的 coupling/临时构建对象边界；对象级精确归因不可用 |
| outer KSP setup ready → all setup objects cleanup | `71.8689 → 16.0022 GiB` | `setup_destroyed=true`，bottom/top factor `0/0`；release order 为 coupling → bottom → top → packet bundle |

以上数值均为 marker-aligned process-tree boundary samples，不是单对象独立因果测量。

## 资源与容量边界

V5-5 streaming-W 的 h4 数字是 derived object capacity：W 总计 `158223360 B`，streaming C action 估算 `97507312 B`，两者对象容量变化约 `60716048 B = 0.0565462261 GiB`。streaming component 证明 W 可不再 resident，但 formal candidate 尚未以该对象策略取得资格；这不是 process-tree saving，也不能解决 V4 iterative 相对 direct 的约 `10.96 GiB` 回归。V5-3 factor-only、V5-4 single modal Schur 与 fixed GMRES 的实现/组件证据也没有 fresh h4 full-solve RSS，因此不能把它们叠加成完整优化收益。

### retained-W 与 streaming-W（synthetic component only）

```math
K = H - D F^{-1} C,
\qquad
y = F^{-1}r + F^{-1}C K^{-1}D F^{-1}r.
```

两种实现使用相同的 `K`；retained-W 每次 apply 保留完整 `W`，streaming-W 不保留 `W`，而在 setup 时按固定 batch 累积修正。streaming 不是改变方程，也不是 h4 formal qualification。

| 项目 | retained-W | streaming-W batch8 |
| --- | ---: | ---: |
| W resident | `32768 B` | `0 B` |
| batch buffer | not applicable | `8192 B` |
| setup factor solves / D applies | `32 / 32` | `32 / 32` |
| apply solves（4 RHS） | `4` | `8` |
| internal wall | `0.01537 s` | `0.01672 s` |
| numerical equivalence | component pass | max error vs retained `1.1145e-20` |

这些是 MPI1 synthetic fixture 的结果；其 `ru_maxrss` 不能外推 h4 process-tree。batch8 只因确定性的 resident buffer 最小而入选，不依据 RSS 噪声宣称正式节省。

0.7 nm/2 TiB 只保留透明 envelope：按 `2048 GiB`，70/80/90% 规划线分别为 `1433.6/1638.4/1843.2 GiB`。已知 air-side W+K/LU `205.049–208.878 GiB` 约占 `10.0–10.2%`，低于 70% line；它只相对旧 `256 GiB` hard-stop 显示高占用，不能推出完整 two-side peak。Full3D factor values-only `3234.18–32341.76 GiB` 的下界已经超过 90% line，但仍是 conditional estimate。缺少真实 0.7 nm side factor、P/T、modal、RHS、recovery、allocator 和 two-side coupling，不能宣称任一完整物理内存线可行；K/LU 时间和 M/channel 增长也没有上界。

V5 的 6h 默认上限适用于组件/正式阶段；本 fixed-budget component 在约 `492.894576008 s` 的 setup/online窗口内因 mandatory numerical Gate 失败而受控停止，未触发 6h timeout，也没有资格使用 8h 延长。BLR family 已因资源失败关闭；V5-8/full solve、top、outer、recovery、field、RTA 均 `not_run/deferred`。

| Gate policy | 实际情况 |
| --- | --- |
| 6h default | fixed-budget 在约 493 s numerical stop，未触发 6h；BLR 资源 stop 也未延长 |
| 8h extension | 仅为满足 outer iterative 条件的政策；本 fixed-budget/BLR/component 没有资格使用，未触发 |
| numerical failure | fixed-budget mandatory traction residual 超 `1e-2`，因此 top/outer/recovery 立即 `not_run` |
| deferred work | V5-8 full formal、Full3D new heavy、0.7 nm PDE、arbitrary-3D qualification |

## 测试与 Gate 口径

| 检查 | 结果 | 口径 |
| --- | --- | --- |
| V5 code-stage focused serial / MPI2 / MPI4 | 沿用对应 clean SHA 的通过证据 | 本最终 turn 未重跑 |
| Ruff / format / compileall | 沿用 `ff89f07b...` 代码阶段证据 | 本轮无 Python 修改 |
| benchmark `--no-write` | fresh rerun `302/302 pass` | 本次 docs/evidence closeout 在 qualified activation 下实际执行 |
| compact JSON / links / fenced math / tables / diff-check | fresh `pass` | 本次 docs/evidence closeout 实际执行 |
| full repository pytest | `not_run` | 不伪造 CI |

详细表格见 [h4 final](outcomes/v5_h4_hybrid_iterative_final.md) 与 [0.7 nm capacity](outcomes/v5_0p7nm_hybrid_capacity.md)。

## V5 顺序与合并边界

V5-8 full formal、Full3D new heavy、0.7 nm PDE、arbitrary-3D qualification 和 third BLR profile 均不运行。后续若重新授权，应先补 side-specific measured evidence，再由主审另行批准，不得把本次 controlled negative 变成 positive。

| 分组 | 建议 |
| --- | --- |
| production-generic candidate（仍需后续逐 hunk review） | telemetry/marker alignment、hash-bound packet/spool catalog validation、collective lifecycle tests；不改变 solver default |
| research-only | factor-only exact handle、single-Schur/GMRES10 explicit opt-in、streaming-W component、fixed-budget orchestration 与 compact records |
| do-not-merge / do-not-promote | BLR profile/campaign、fixed-budget numerical-negative candidate、未完成 top/outer/recovery、raw heavy artifacts |
