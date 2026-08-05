# Task037 Review V2 阶段回应

## 1. 当前结论

`f27a49131ae8e9ada12c3678d55f82dad96c3133` 是 Candidate C 与本轮正式数值证据的 pre-closeout clean source SHA；本文由独立 docs/evidence commit 收口并推送，最终文档 commit SHA由交付报告给出，不改变该数值源码。

结论是 `PRECONDITIONER_INSUFFICIENT_AFTER_CONTROLLED_FUNNEL`：p6 factor-free 与 p2 exact-sequence auxiliary 的节省矩阵/因子内存机制已在 screen 中得到证据，但 A、B2、B4、C 都没有得到可替代 direct 的收敛迭代解。因此 whole-branch merge recommendation=NO，production qualification=NO。

## 2. V2 共识执行矩阵

| 候选 | 做了什么 | 20 步 | 100 步 | 200 步与淘汰点 |
|---|---|---|---|---|
| A | 现有 p2 auxiliary + diagonal pre/post | pass；`0.9798706637378245` | fail；`0.9625338200823326` | not_run；A 因 screen100 淘汰 |
| B2 | p6 factor-free local slab action，固定 2-step Krylov，p2 auxiliary | pass；`0.4263392615374972` | pass；`0.26452427778264737` | fail；true=`0.20957190163452238`，prediction=`3845`/`9027.507786733306 s` |
| B4 | B2 的唯一 fixed-4-step 升级 | pass；`0.42611925267187817` | pass；`0.17083264476239823` | fail；true=`0.1405734647596501`，prediction=`6524`/`26451.930413699356 s` |
| C | B4 + one-hot deterministic RAS/optimized Schwarz | pass；`0.4631648828112781` | pass；`0.18562438468519604` | fail；true=`0.1488668017254931`，prediction=`not_generated` |

200-step Gate 要求 true residual `<=0.05`、last-40 log-linear prediction `<=3000` iterations、formal wall prediction `<=7200 s`。B2 与 B4 三项均有正式失败；C 的 200-step true residual 失败，且本次 runner 没有生成 prediction 字段。A 没有进入 200-step。

## 3. 原始证据与资源

详细逐 artifact 绑定见 [V2 compact record](../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_v2_preconditioner_funnel_v1.json)。下表只列 process-tree simultaneous RSS authority；worker RSS/PSS/USS 保留在 record 与原始 watchdog summary 中。

| 候选/步数 | MPI8 artifact | source SHA | authority GiB | worker RSS/PSS/USS MiB | wall s | 状态 |
|---|---|---|---:|---|---:|---|
| A/20 | `m4_p2_auxiliary_screen20...a9bca762` | `a9bca762` | `6.311897277832031` | `6448.7695/5139.5020/4941.5859` | `128.0054491769988` | screen pass |
| A/100 | `m4_p2_auxiliary_screen100...cbffa088` | `cbffa088` | `6.310966491699219` | `6447.8359/5139.6074/4941.7188` | `135.5684759989963` | screen not_pass |
| B2/20 | `m4_p2_factor_free_slab_screen20...71587826` | `71587826` | `6.322399139404297` | `6459.4805/5150.5654/4955.8320` | `160.34715404803865` | pass |
| B2/100 | `m4_p2_factor_free_slab_screen100...71587826` | `71587826` | `6.435756683349609` | `6575.5430/5263.8867/5065.5938` | `297.93973794498015` | pass |
| B2/200 | `m4_p2_factor_free_slab_screen200...71587826` | `71587826` | `6.336677551269531` | `6474.1211/5163.3936/4965.3828` | `469.57127629301976` | not_pass |
| B4/20 | `m4_p2_factor_free_slab_steps4_screen20...88027721` | `88027721` | `6.275825500488281` | `6411.8516/5102.9570/4909.1875` | `190.66914244904183` | pass |
| B4/100 | `m4_p2_factor_free_slab_steps4_screen100...88027721` | `88027721` | `6.325313568115234` | `6462.4844/5152.2998/4953.9414` | `457.908051176928` | pass |
| B4/200 | `m4_p2_factor_free_slab_steps4_screen200...88027721` | `88027721` | `6.3277435302734375` | `6464.9727/5153.5996/4955.2578` | `810.9114167289808` | not_pass |
| C/20 | `m4_p2_factor_free_slab_candidate_c_ras_screen20...f27a4913` | `f27a4913` | `6.472965240478516` | `6613.6797/5304.5361/5106.8164` | `192.31425288401078` | pass |
| C/100 | `m4_p2_factor_free_slab_candidate_c_ras_screen100...f27a4913` | `f27a4913` | `6.338722229003906` | `6476.25/5164.3057/4976.25` | `463.9838331990177` | pass |
| C/200 | `m4_p2_factor_free_slab_candidate_c_ras_screen200...f27a4913` | `f27a4913` | `6.338939666748047` | `6476.5078/5165.1318/4967.9297` | `801.1166084950091` | not_pass |

All runs report swap=0, no memory termination, and no official R/T/A. The approximately 6.3 GiB values are MPI8 screen process-tree peaks, not a peak for a completed converged solve.

## 4. Candidate C 的关键诊断

Candidate C 保留 16 slabs、overlap `0.125`、p2 MUMPS、75D wave coarse、right FGMRES restart `90` 与 local fixed `4` steps。其真实 p6/h10 audit 为：

| 字段 | 实测值 |
|---|---:|
| active/interface rows | `51192 / 51192` |
| `interface_shift_mode` | `shared_rows_only` |
| interface/non-interface shift nonzero rows | `51192 / 0` |
| RAS core sum error | `0.0` |
| p6 matrix/factor/NNZ | `false / 0 / 0` |
| p2 factor/matrix | MUMPS `1`；rows `4680`；matrix NNZ `477216` |
| global A/F | `false / false` |

这意味着 shared-only Robin shift 在该几何上并没有只作用于少数 interface rows，而是覆盖全部 active rows；C 的实质新增机制主要是 one-hot RAS 回写。C 在 100 步为 `0.18562438468519604`，在 200 步为 `0.1488668017254931`，均比 B4 对应的 `0.17083264476239823` 与 `0.1405734647596501` 更差。

## 5. 结果边界

- 四类运行均为 MPI8、screen-limited、research-only；KSP reason 为 max-it，不能写成 full solver success。
- `official_result=false`、postprocess/RTA 未运行；没有可用的 official R/T/A。
- A 因 screen100 Gate 失败；B2、B4、C 因 screen200 Gate 失败。因此各自后续 full、restart `90→60→40→30→20` 与 MPI1 full 全部 `not_run`。这是 review funnel 的受控停止，不是执行遗漏。
- 不把 p6 factor-free 的内存证据升级成 production-qualified solver；不把低阶 PC、Hybrid 或 0.7 nm 写成可用路线。

## 6. 测试与源码边界

Candidate C 最终源码绑定 `f27a49131ae8e9ada12c3678d55f82dad96c3133`。已完成的轻量 Gate：serial `test239` 6 passed；test223 三个直接节点 3 passed；MPI2 每 rank 3 passed/3 skipped；Ruff/format/compileall/diff-check pass。按用户要求没有运行 full repository pytest；本次文档收口不重复昂贵 targeted/PDE 测试。

本轮相关提交按当前分支历史核实：

| 阶段 | commit |
|---|---|
| C1 factor-free local slab Krylov oracle | `b3861189717cbee7f82a0bd8e6fac14e97c49157` |
| C2 p2 + factor-free composition | `b7ed5e581339c3a39323cfd48dd0f9a22240ffa8` |
| C3 core profile integration | `ff495d7c9470d89f0abfb95d1cf4cd37e28051c5` |
| C4 watchdog profile | `71587826b464ea6204ae17fee0325ca27dd6633b` |
| B4 fixed four-step candidate | `88027721819d3662fa9bd0a992b9fbf7badefed3` |
| C optimized Schwarz/RAS candidate | `f27a49131ae8e9ada12c3678d55f82dad96c3133` |

数值证据绑定的 pre-closeout source 是 branch `codex/20260803-task37-matrix-free-iterative-development`、SHA `f27a49131ae8e9ada12c3678d55f82dad96c3133`。本轮 closeout scope 仅为 compact evidence 与回应文档；最终文档 commit SHA由交付报告给出。

## 7. 同意、延期与不同意

| 决定 | 内容与边界 |
|---|---|
| 同意并完成 | p6 factor-free action、true p2 exact-sequence auxiliary、bounded local Krylov、恰好一个 optimized Schwarz C。 |
| 同意但延期 | matrix-free DtN 留给 P3/P5；partial/uncondensed fallback 作为独立 bounded study；exact factor reuse/complex64 另行资格化。它们不是本轮结果。 |
| 不执行 | 重开 M4d、宽参数扫描、把任何低秩/迭代 Hybrid 或本候选标 production；前者已有受控 negative，后者没有通过 200/full Gate。 |

## 8. 最终建议

V2 没有得到可替代 direct 的收敛迭代解；预条件器不足，而 factor-free p6 storage 机制有效。建议停止在同一 static-condensed Schwarz 家族继续微调，后续是否做 partial/uncondensed interface study 或其他路线交由新 review 决定，本轮不擅自开发。

本轮 closeout 由独立 docs/evidence commit 承载；不改变 ordinary defaults，不写 response_v1，不启动 full/MPI1/PDE。
