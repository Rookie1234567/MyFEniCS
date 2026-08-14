# Task37 Extra Development V11 收口响应

## 授权与结论

用户明确授权原文为：“我允许你继续正式允许，不用管v11里的限制，继续执行任务”。按上下文解释为：用户允许继续正式运行并越过 V11 中被点名忽略的阶段/次数限制。据此，用户授权越过 V11 的正式运行次数限制、M2→M3 阶段锁和 84 个完整 882D packed factor 限制，并现已明确授权继续 M4–M6 正式研究。该授权不放宽 full-space、数值、RSS `<2,000,000,000 B`、swap=0、true residual `<=1e-6`、physics 或 provenance Gate，也不允许把容量或数值负结果包装成 execution-fix。

| 项目 | 当前结论 |
| --- | --- |
| working branch | `codex/20260806-task37-iterative-extra-development` |
| latest code/source before this response | `a3c677f0777eb858ac8b3435fec4cff92f29d9f3`（M5 formal source；本次文档提交前的 clean code SHA） |
| M4Y formal source | `766154ae731ee9fac6d23492801ed7ac6e318616` |
| previous M1 closeout source | `cc0573ba34cee13b1eb3b8dc8e51ac7e7cbe0dfc`（承接 `949494c...` 的历史文档/代码提交） |
| M1 formal source 1 | `ad589ca1e7d473e6ed77827f8bb23410f21c38a9` |
| M1 execution-fix formal source | `caed4dea78e9d9a924e2ad06daba9dd635801e94` |
| M1 latest dual-fixture fix | `949494c73d1c6ece397471f0f0ccc96f78cc1d79`；已由当前 v2 formal/checker 资格化 |
| M3Y code chain | `12777a724...` → `b8afa94...` → `404f6c6a...` |
| formal budget | 原 V11 次数限制由用户本轮明确授权忽略；其余 Gate 全部保留 |
| M1 最终状态 | `PASS / QUALIFIED`（v2 checker 15/15） |
| M2 最终状态 | `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED`；checkerboard source 超过 `0.70` |
| M3Y packed full-store | `PASS / QUALIFIED`（明确授权的 research-only lane） |
| M4Y packed patch PC | `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED`；checkerboard source 超过 `0.70` |
| M4Y-W 固定权重诊断 | `BEST_CASE_STRUCTURE_DIAGNOSTIC_ONLY / not_formal_pass` |
| M5 第一屏 | `PASS / COERCIVE_TARGET_MET_WITHOUT_COARSE`；checker 26/26 |
| M6A matrix-free DtN | `PASS / QUALIFIED`（仅 action/DtN authority，非 PDE/RTA/full-memory pass） |
| M6B/time-harmonic/PDE/RTA/final `<2GB` | `not_run_yet`；已获用户授权继续正式研究 |
| docs commit | `this_response_commit (exact SHA reported in final handoff)` |

历史 execution-fix raw 的 p4 canonical adjoint 曾失败；随后用户授权继续 formal-count 范围内的正式研究。M1 v2 仍是正式 `PASS / QUALIFIED`，M2 high-complement oracle 的 checkerboard source 触发正式数值 Gate 失败，因此 M2 为 `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED`。在该失败之后，用户又明确授权执行独立的 M3Y packed-store research lane；M3Y checker 正式通过。随后 M4Y 正式运行，但 checkerboard source 再次触发数值 Gate，故 M4Y 为 `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED`；M4Y-W 只提供结构诊断，不改变该结论，也不代表 PDE 目标通过。所有结论均不放宽数值、容量、RSS、swap 或 provenance Gate。

## 继承的冻结结论

以下结论沿用 V9/V10，不在本响应中重算或弱化：G2=`G2_FAIL`；G3 additive LOR-HX=`prohibited`；old G4=`prohibited`；H1R3 系列已通过；V8 fixed-unit H2B 为 numeric fail；V9 S0 direction 为 fail；P0 只资格化了代表性 representative；C1 canonical lane 曾因 candidate/capacity Gate 受控停止。ordinary default 未改变，research-only 路径不提升为 production。

## M1 正式运行与 checker

| 运行 | 实测结果 | 资源/身份 | 结论 |
| --- | --- | --- | --- |
| initial formal run1 | source `ad589ca...`；MPI1 image `0.31070811280298904`，adjoint `1.6018790302711856e-17`；MPI2 未运行 | MPI1 peak `510,328,832 B`，swap=0，进程退出；worker RC=1 | 旧 affine 本身低阶、可由 p4 表示，但不满足非平凡 Floquet 边界，因而不是合法 constrained-p4 manufactured fixture；归类为 fixture/execution construction failure，不把 image 值当 transfer 科学负结果 |
| execution-fix formal run1 | source `caed4dea...`；MPI1 image `5.468843900583829e-15`、adjoint `3.1471318267200023e-17`；MPI2 image `5.757606853614202e-15`、adjoint `1.521528936022671e-17`；两边 finite/deterministic | MPI1 peak `521,723,904 B`，MPI2 peak `974,729,216 B`，swap=0，RC=0，进程均退出；p4/p6 rows `53,084/173,802`，constraints `4,124/9,210` | worker 的 p6 image 和普通数值 Gate通过，但 checker 重算 p4 canonical adjoint relative L2=`0.9503885989179789`，故 M1 `gate_failed` |

历史 execution-fix checker 的冻结 record 为 `status=gate_failed`、`pass=false`，15 项 checks 中 14 项为 true；该负结果永久保留。当前 v2 checker 为 `status=pass`、`pass=true`、`problems=[]`，15/15 checks true；p6 canonical relative L2=`1.982326002916046e-15`，p4 canonical adjoint relative L2=`1.3580087229674401e-15`，missing/extra/duplicate 全部 `0/0/0`。

当前 v2 运行的资源为 MPI1 peak `521,449,472 B`、MPI2 peak `953,028,608 B`、swap=0、processes_gone=true；retained transfer payload 为 `18,244,384 / 15,574,480 B`，bounded workspace 为 `3,046,112 / 1,757,632 B`。raw source 与 checker source 均 clean、均为 `cc0573ba34cee13b1eb3b8dc8e51ac7e7cbe0dfc`。

## M2 正式运行、checker 与数值边界

M2 的通俗含义是：把一个完整的 882 维局部 patch 分成低阶 300 维部分和高阶 582 维补空间，只对高阶补空间保存一个 factor，检查它能否把五类固定 source 的 patch residual 降到要求。它不是全局 PDE solve，也没有物化 global matrix、Schur、slab factor 或 KSP。

| 项目 | 实测结果 |
| --- | --- |
| formal source | `b4c1c6c76d667dac78e5dc384b302026379cb8d2` |
| raw | `benchmarks/artifacts/task037_extra_development/m2_b4c1c6c_statm_run1` |
| watchdog | `PASS`；stage/online worker `RC=0` |
| checker | `RC=1`；`status=gate_failed`；`problems=["source_gate"]` |
| stage | peak `1,296,175,104 B`，swap `0`，RC0 |
| online | peak `848,654,336 B`，swap `0`，RC0 |
| scope | 252 cells、173,802 rows、9,210 constraints、central `3`/class `3`/touching `19` |
| split | `rank(QL)=300`、`rank(QH)=582`；Q orthogonality `9.257892486599041e-16`；split reconstruction `9.637068547580966e-16` |
| factor | values+pivots `5,421,912 B`；factor residual `5.725553567915199e-16`；solve residual `6.773813153765502e-13` |
| retained transform | `12,446,784 B` |

| source | low/high energy | formal rho | action closure | 结论 |
| --- | ---: | ---: | ---: | --- |
| gradient-dominated | `0.7476937969517845 / 0.25230620304821527` | `0.6501331033379294` | `3.731727295429185e-14` | PASS |
| curl-dominated | `0.6568811348518978 / 0.34311886514810186` | `0.5370997972508667` | `4.765947835467422e-14` | PASS |
| mixed | `0.7350021241367845 / 0.26499787586321516` | `0.6350618866926864` | `3.9933950843220025e-14` | PASS |
| checkerboard/high-frequency | `0.6666666666666659 / 0.3333333333333332` | **`0.7319752447810908`** | `1.1012012738647016e-13` | **FAIL，超过 `0.70`** |
| physical-RHS-like | `0.6338129814899229 / 0.3661870185100772` | `0.5038880312320936` | `4.8627220733002086e-14` | PASS |

因此 M2 的正式分类是 `FORMAL_NUMERIC_FAIL`，不是 timeout、JIT、API、RSS、swap 或 resource failure。compact 的机器字段仍保留 `status=gate_failed`、`pass=false`、`problems=["source_gate"]`；这里的 source Gate 失败由 checkerboard 的实际 `rho` 触发，不能改写为 PASS。

## M2 固定离线诊断边界

两份 `/tmp` 诊断均为 `BEST_CASE_DIAGNOSTIC_ONLY / not_formal_pass`，没有改变正式 M2 FAIL：

| 固定结构 | checkerboard 结果 |
| --- | ---: |
| row-complete low→high | `0.7365588632365486` |
| fixed A directions 的 joint2 least-squares | `0.7314868062038236` |
| fixed three-action symmetric LHL | `0.7318570005704766` |
| exact patch inverse sanity | `2.1656111107723205e-12` |

这些结果排除了“只补 low 阶段即可恢复 M2”的解释；这些旧离线诊断本身不构成 M3Y 资格，资格来自本轮正式 raw/checker。M3Y 已由用户越过阶段锁后正式通过；M4Y 已完成正式运行但因 checkerboard 数值 Gate 失败而 `NOT_QUALIFIED`；M5 第一屏随后正式通过，M6A action/DtN 也已由独立 checker 正式通过；M6B、time-harmonic PDE、RTA 和 full PDE process-tree RSS 仍为 `not_run_yet`/`not_measured`。

## 两个 fixture/provenance 缺陷

### 1. source fixture

初始 formal 使用的 affine source 本身低阶、可由 p4 表示，但其 Floquet 边界不成立，因而不是合法 constrained-p4 manufactured fixture。诊断中旧 affine negative control 的边界 max abs 为 `33.76939473850167`、relative 为 `1.5286148007984073`。改用 cfg-bound 的 `qx*qy*c` 低阶多项式后，边界 max abs=`1.1102230246251565e-16`，raw p4→p6 relative=`5.102448959291011e-15`，transfer→独立 p6 expected relative=`5.466792763091917e-15`。这一窄修复落在 `caed4dea78e9d9a924e2ad06daba9dd635801e94`，没有放宽任何 Gate 或改变 transfer/MPC。

### 2. dual fixture

execution-fix 之前的 dual 使用 DOLFINx global dof id 生成值；global numbering 会随 MPI partition 改变。诊断中相同 canonical keys 的 global id 有 `72,840/164,592` 不同，即 `44.25488480606591%`；旧 dual input canonical relative=`0.9091583071292413`，旧 adjoint output relative=`0.9503885989179789`。改为 cfg-bound、固定的 `floquet_compatible_degree5_dual_v1` 后，manufactured dual input relative=`1.647661415080129e-15`，manufactured adjoint output relative=`1.3580087229674401e-15`，missing/extra/duplicate 均为 `0/0/0`。修复 commit 为 `949494c73d1c6ece397471f0f0ccc96f78cc1d79`；该修复已在 `cc0573b` clean source 的 M1 v2 formal/checker 中正式通过并资格化，同时保留旧 negative formal evidence。

### 诊断边界

orientation diagnostic 中 252 个 cell 有 82 个 nonzero `cell_info`，但 current-vs-prescribed max abs=`8.616549110757854e-15`，因此没有证据支持 orientation 是根因。MPC commutation diagnostic 显示 carrier 与 DOLFINx lift 的 p4/p6 系数误差均为 `0`、master binding mismatch 为 `0`，且完整 transfer 与 `C6 P0 C4` 的 relative error 为 `0`。这些诊断解释了已观测的失败路径，但不能把未正式运行的最新 code 变成资格化结果。

## M4Y 正式 packed-patch PC

M4Y 的通俗含义是：复用 M3Y 的 84 份只读 packed Cholesky 因子，让 252 个 cell patch 先各自解一个局部问题，再按重叠计数合并为一个 full-space 修正，并只调用一次真实的 `B0` action 来做固定权重缩放。这样可以在不组装 global matrix、Schur 或 trace slab 的情况下控制内存；但“能低成本产生修正”不等于“修正能消除所有困难误差”，正式 checkerboard Gate 仍须单独通过。

| 项目 | 正式结果 |
| --- | --- |
| source / raw | `766154ae731ee9fac6d23492801ed7ac6e318616` / `benchmarks/artifacts/task037_extra_development/m4y_766154a_run1` |
| watchdog | `RC=0`，`status=pass` |
| checker | `RC=1`，`status=gate_failed`，`pass=false`，`route=M4Y` |
| 分类 | `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED` |
| 运行边界 | 不是 execution、JIT、RSS、swap 或 resource failure；M4Y-W 也不改写该负结果 |

| source | rho | limit | repeat | wall ratio | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| gradient-dominated | `0.5726363196244373` | `0.90` | `0` | `1.0648731722995044` | PASS |
| curl-dominated | `0.5119565347353272` | `0.90` | `0` | `1.0527972304686382` | PASS |
| mixed | `0.5651932967410976` | `0.80` | `0` | `1.0546199852088745` | PASS |
| checkerboard/high-frequency | **`0.9931217079734292`** | **`0.70`** | `0` | `1.0540019605701865` | **FAIL** |
| physical-RHS-like | `0.4860142993018098` | `0.90` | `0` | `1.061045779894205` | PASS |

唯一正式数值失败是 checkerboard：`0.9931217079734292 > 0.70`。五个 source 的 correction/action repeat 均为 `0`，并且数组、omega 和 action telemetry 已由 checker 重算。compact 中的 `independent_recompute=false` 是 checker 将“所有 source Gate 合并后的最终布尔”记录为 false；它不表示数组或 omega 的独立重算彼此不一致。除 source Gate 及其派生的最终 independent-recompute 标记外，其余结构 checks 均通过。

| 资源/身份 Gate | 实测 |
| --- | ---: |
| isolated stage peak / online peak | `1,290,907,648 B` / `909,246,464 B` |
| stage / online watchdog | `RC0` / `RC0`，process gone=true / true |
| swap | `0` |
| M3Y retained store | `525,196,562 B` |
| evidence workspace | `69,520,800 B` |
| M4Y PC workspace | `11,151,552 B` |
| 252 cells → 84 factors | reuse `168`，copy `0` |
| materialization | global matrix、global constraint、cell Schur、slab、KSP、DtN、PDE 均 `false`；`fine_space=uncondensed_fullspace`，`ordinary_default=false` |

上述 `909,246,464 B` 是 M4Y online process-tree peak，不是 PDE peak；full PDE、true residual、直接法物理对照和 PDE process-tree RSS 尚未测量。

最终代码后的 focused 实现验证合计 `18 passed`（`test309`、`test307`、`test308`、`test294`）；相关 `compileall`、AST duplicate-literal-key 和 `git diff --check` 均 pass。Ruff unavailable，full repository pytest 为 `not_run`。这些是实现回归结果，不构成 M4Y formal qualification。

## M4Y-W 固定权重位置诊断

M4Y-W 只比较三种预先固定的合并权重：正式的左侧 PoU、无权 additive Schwarz，以及左右各除以平方根重叠计数的 symmetric sqrt-PoU。它们都只做一次真实 `B0` action；没有调参、线性组合、颜色顺序或候选选择。因此状态固定为 `BEST_CASE_STRUCTURE_DIAGNOSTIC_ONLY / not_formal_pass`，不构成 M4Y qualification，也不宣称 SPD 资格。

| source | limit | A current left-PoU | B unweighted | C symmetric sqrt-PoU |
| --- | ---: | ---: | ---: | ---: |
| gradient-dominated | `0.90` | `0.5726363196244373` | `0.6522833075546219` | `0.5389466254290002` |
| curl-dominated | `0.90` | `0.5119565347353272` | `0.5860664196870441` | `0.5006462879867353` |
| mixed | `0.80` | `0.5651932967410976` | `0.644166345359071` | `0.534162054038329` |
| checkerboard/high-frequency | **`0.70`** | **`0.9931217079734292`** | **`0.9602175114`** | **`0.9732722411`** |
| physical-RHS-like | `0.90` | `0.4860142993018098` | `0.5544966067454279` | `0.4825702522346798` |

诊断最大 RSS 为 `886,696 KiB`，swap=`0`。A 逐位复现正式 M4Y 的 correction/action 结果；B、C 的 checkerboard 仍分别高于 `0.70`，所以仅改变权重放置不足以压制该高频模式。这个结论只说明当前 local-PC 结构与该 source 的误差模式不匹配，不证明任何未运行的 SPD、global solver 或 PDE 资格。

| M4Y-W provenance | SHA |
| --- | --- |
| script | `56ae70156cb5bf27dd3ebdee194233b7fc2554135b21d29bc50f370a6281b1b0` |
| JSON | `78a8bbf4ec4ffa4b8aa6a9ff9e55ffca7bbd01fcb050e199c23b9cc9a7e1b1dd` |
| stdout | `ad83738cc4acf9fbb6e535bcafbd72a0a1623dca6bdc74e44dca15296ae62f01` |

## M4Y 证据索引

| 证据 | 路径 / SHA |
| --- | --- |
| M4Y watchdog | `benchmarks/artifacts/task037_extra_development/m4y_766154a_run1/m4y_watchdog_summary.json`；`f56a0b0fb607d07045362d9dce4dc62174e57992c0af779e9a57b0099d92b03c` |
| M4Y worker | `benchmarks/artifacts/task037_extra_development/m4y_766154a_run1/m4y_worker_summary.json`；`e37bacc6901faefa7844aa2a2894011f5da7ffcf623a1c6d4d5d4ffd32e778c4` |
| M4Y online timeline | `benchmarks/artifacts/task037_extra_development/m4y_766154a_run1/online_timeline.json`；`cd7dbe1c41a1505cfc842aeed9ed911cd9f82a2eb79bab0e0fa048db69fe7bad` |
| M4Y compact | `benchmarks/cases/101_task37_extra_development/records/m4y_full_packed_patch_pc.json`；`7c227b67f288ca88990f1bc966f1266ff28eb280d0bc9623ab1354f527634812` |
| M4Y raw tree digest | raw tree digest `7db097d4c894e152753ab3c3a618f6556fd1cebec50fff6fbb2bee359e2d6580` |
| frozen M2 compact | `benchmarks/cases/101_task37_extra_development/records/m2_high_complement_patch_oracle_v2.json`；`ebd512aa0e4b6823d5d95c5f816cc6e898c9fd97392af4f7346c83ba3ac4e31f` |

## M4Y 之后的边界

用户已明确授权继续独立 M5/M6 research lane；这不把 M4Y 的 `FORMAL_NUMERIC_FAIL` 改成 PASS，也不放宽 `<2,000,000,000 B`、swap=0、true residual、physics 或 provenance Gate。M5 第一屏和 M6A action/DtN 已分别正式通过；M6B、time-harmonic PDE、RTA、full true residual、direct-authority physics comparison 和最终 PDE process-tree RSS 仍为 `not_run_yet`/`not_measured`。75D coarse 因 iter100 true residual 已低于 `1e-8` 且没有传播型平台而 `not_needed/not_run`，不是 75D 资格化。ordinary default 未改变；不得把 M4Y-W、M5 或 M6A 的 online peak 当作 PDE qualification。

## M5 coercive global FGMRES 第一屏

M5 第一屏用固定 coercive full-space 算子 `B0 = Kcurl + k0^2 M_abs_epsilon` 检查一个右预条件 FGMRES 是否能把真实残差持续压低。FGMRES 允许预条件器随当前 residual 改变，因此这里不能把 PETSc 内部 monitor norm 当作最终依据；每个 checkpoint 都重新做真实 `B0` action，checker 再从保存数组独立计算 `rhs-B0*x`。

| 项目 | 正式实测 |
| --- | --- |
| source | `a3c677f0777eb858ac8b3435fec4cff92f29d9f3` |
| scope | MPI1、p6/h10、252 cells、173,802 rows、882 local rows、9,210 constraints |
| outer solver | right FGMRES，restart=20，max_it=100，unpreconditioned norm |
| fixed screen | `rtol=0`、`atol=0`，checkpoint `20/50/100` |
| watchdog | RC0，`status=pass`，elapsed `1185.6522394389904 s` |
| checker | RC0，`status=pass`，26/26 checks true，`problems=[]` |
| 分类 | `M5 FIRST_SCREEN_PASS / COERCIVE_TARGET_MET_WITHOUT_COARSE` |

| checkpoint | worker reported | checker true residual | Gate |
| --- | ---: | ---: | --- |
| iter20 | `1.2075357244328856e-4` | `1.2075357244328856e-4` | `<=0.40` PASS |
| iter50 | `3.1216557608039517e-6` | `3.121655760822562e-6` | 中间下降 |
| iter100 | `2.9165492426098423e-9` | `2.916549231606929e-9` | `<=1e-3` PASS |
| iter50 → iter100 | — | 严格下降 | PASS |

`converged_reason=-3` 是固定 `rtol=atol=0`、`max_it=100` 达到预算后的预期 `DIVERGED_ITS` 终止语义，不是 positive PETSc convergence；正式 PASS 依据是 checker 独立重算的 explicit true residual 与资源/架构 Gate。

| 资源/架构 | 实测 |
| --- | --- |
| stage / online peak | `1,183,698,944 B` / `978,083,840 B` |
| swap / cleanup | `0 / 0`；stage、online processes gone |
| operator / PC / sample actions | `108 / 100 / 3`；总 action `209=1+108+100` |
| M3Y store | 84 factors、252 cells、`525,196,562 B`、mmap read-only |
| factor reuse / copy | `168 / 0` |
| PoU closure | `0.0` |
| materialization | global matrix、static condensation、trace slab、Schur、DtN、coarse、PDE 均 false |
| fine space / default | `uncondensed_fullspace` / `ordinary_default=false` |

固定 physical-RHS-like source 的 SHA 是 `6f91c83e1722a07958e6d757f7aa13f88858c95ea9ff88fe9e8693629b6f2c6d`。M4Y 仍为 `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED`，M5 是用户 override 后开启的独立 research lane，不改写 M4Y 负结果。

iter100 已低于 `1e-8`，且没有传播型平台，所以固定 75D wave coarse 为 `not_needed/not_run`，不是 75D 已通过。M5 第一屏和 M6A action/DtN 均不是 PDE 或 official physics qualification；M6B、time-harmonic PDE、RTA、direct-authority physics comparison 和最终 PDE `<2,000,000,000 B` 目标仍未运行/未测量。

| M5 证据 | 路径 / SHA |
| --- | --- |
| raw | `benchmarks/artifacts/task037_extra_development/m5_a3c677f_run1` |
| watchdog summary | `m5_watchdog_summary.json`；`ccda2b2ab38b175f15fc40b28575ac21cf39ebd5fe492adf77eb8d4e34c242a7` |
| worker summary | `m5_worker_summary.json`；`8b26af2962183ca8bc85734cd593d67cf899022813f7c85f6069db8ba12d4556` |
| stage summary | `stage_summary.json`；`410ce5a6763e14be5c505c192509a5b8672d52e41af10a48b259a0fa51309d37` |
| timeline | `m5_timeline.jsonl`；`03c06817c2f076933708c4d1d57864db21e2a0452475747fd302f630aecac39b` |
| raw evidence | `b384cfa89b934618eb9d0e8f2cceea9ca5b4f8926684f232d8e7c084471ea85b` |
| compact | `benchmarks/cases/101_task37_extra_development/records/m5_coercive_fgmres_screen.json`；`822c2d2af336395fc85fbfec99567029f29092be3413cd60da6c19beb4b901dc` |

## 实现与测试收口

本次收口文档阶段未再改代码、不改旧 checker、不启动任何 formal/checker/MPI/PDE。本轮代码修复提交明确为：`caed4dea78e9d9a924e2ad06daba9dd635801e94`（source fixture）和 `949494c73d1c6ece397471f0f0ccc96f78cc1d79`（dual fixture）。最终代码变化后运行的 focused 验证如下；这些是实现回归，不构成 M1 qualification。

| 验证 | 实际命令 | 结果 |
| --- | --- | --- |
| `test305` | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_305_task037_extra_m1_harness.py` | `12 passed` |
| `test304` MPI1 | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_304_task037_extra_p_split_owner_transfer.py` | `6 passed, 1 skipped` |
| `test304` MPI2 | `source scripts/activate_myfenics_wsl.sh && mpiexec -n 2 python -m pytest -q src/test/test_304_task037_extra_p_split_owner_transfer.py` | 每个 rank `6 passed, 1 skipped` |
| `test303 + test227` | `source scripts/activate_myfenics_wsl.sh && python -m pytest -q src/test/test_303_task037_extra_m0_p4_p6_transfer_fixture.py src/test/test_227_task037_canonical_vector_artifacts.py` | `6 passed, 2 skipped` |
| `compileall` | `source scripts/activate_myfenics_wsl.sh && python -m compileall -q benchmarks/canonical_vector_artifacts.py benchmarks/run_task037_extra_m.py src/solvers/hcurl_canonical_vector_dolfinx.py src/solvers/hcurl_p_split_owner_transfer.py src/test/test_304_task037_extra_p_split_owner_transfer.py src/test/test_305_task037_extra_m1_harness.py` | pass |
| `git diff --check` | `git --git-dir=.git-codex --work-tree=. diff --check` | pass |
| full repository pytest | 未运行 | `not_run` |

`949494c...` 的边界是“dual fixture 已改为 partition-independent”，不是“formal M1 已通过”。

旧 formal raw 目录和旧 negative record 永久保留；`m1_fullspace_p4_p6_transfer.json` 原字节保留，file SHA 为 `ad4184d82743a3063d426ad2bd2c2e582c5c3f6f5d8999548cf2d81d704422b0`，其 status 仍为 `gate_failed`，不能改写为 pass。当前新增 v2 compact file SHA 为 `6ed2c394fc0e04ed1222024bb1cc89281d6c77ac9be28e07451312906107cf72`，embedded evidence SHA 为 `2820715b3d30d54ee7af9169884b4cf562fbb969c0be31bb2238304366cf56ba`。

## M3Y packed row-complete factor store

M3Y 的通俗含义是：对每个 882 行完整局部 patch，不长期保存一个 882×882 方阵 factor，而只保存其 lower packed complex128 Cholesky 三角因子；fresh loader 用 mmap 和三角 solve 读取它，packed action 由 checker 独立重算。它解决的是 84 个局部 factor 的存储问题，不是把局部证据变成全局 PDE 结果。

| 项目 | 正式结果 |
| --- | --- |
| 授权与边界 | 用户明确授权越过 V11 的 M2→M3 锁和 84-factor 研究禁令；M2 `FORMAL_NUMERIC_FAIL` 保持不变，其他 Gate 未放宽 |
| fixed scope | degree=6、`h_nm=10.0`、MPI1、252 cells、24 classes、84 neighborhoods、173802 global rows、882 local rows、9210 constraints |
| source / checker | `404f6c6a5326219bcf6aca098b332b68214781a3` / 同一 clean SHA |
| formal raw / compact | `benchmarks/artifacts/task037_extra_development/m3y_404f6c6_run1` / `benchmarks/cases/101_task37_extra_development/records/m3y_full_packed_patch_store.json` |
| final status | `M3Y PASS / QUALIFIED`，仅指本 research-only packed-store lane |

| Gate | 限值 | 实测 |
| --- | ---: | ---: |
| isolated JIT stage RSS | `<1,800,000,000 B` | `1,280,749,568 B` |
| builder RSS | `<1,800,000,000 B` | `1,068,343,296 B` |
| fresh loader RSS | `<1,050,000,000 B` | `575,459,328 B` |
| swap / cleanup | `0 B` / process gone | `0 B` / `true` |
| factors / packed bytes | `<=96` / formula `882*883/2*16` | `84` / `523,357,632 B` |
| metadata/mapping / retained total | retained `<=560,000,000 B` | `1,838,930 B` / `525,196,562 B`，PASS |
| max action closure / solve residual | `<=1e-11` | `8.402445013054496e-12` / `8.402445013054496e-12`，PASS |
| predicted builder/online live set | `<=1,750,000,000 B` | `1,346,005,004 B`，`predicted`，不是实测 |

builder 对 84 个 row-complete patch 流式生成 packed factor，抽样 neighborhood `0/41/83` 的重复 matrix/factor SHA 一致；全部 84 个 factor 的 solve/action 均记录为 finite、deterministic。loader 对 factor 文件做 read-only mmap 和 solve，checker 独立重算 packed action。`full_dense_factor_count=0`、`pivots=false`、patch/global matrix、global constraint matrix、Schur、static condensation、trace slab、QL/QH transform 和 per-cell factor 均为 `false`。独立 `m3y-check` 返回 RC0，compact 的 20/20 checks 为 `true`，`problems=[]`。

M3Y 代码提交链为 `12777a72497a98576bcb8caa15d58b13a0c837c0`（初始实现）、`b8afa94dd93fca3336660c1e78c52021843acf92`（checker/resource 收紧）和 `404f6c6a5326219bcf6aca098b332b68214781a3`（最终 packed BLAS action 修正）。正式前轻量验证为 `39 passed`，compileall、AST duplicate-key 和 diff-check 均通过；Ruff 不可用。该 PASS 不等价于 PDE qualification，也不改变 ordinary default。

## 证据索引

| 证据 | 路径 / SHA |
| --- | --- |
| initial raw | `benchmarks/artifacts/task037_extra_development/m1_ad589ca_run1`；watchdog `d9fc27103c8fe4fd3668e0d64e1d46c19235d1ee5b4b4767218e98be42798cb4` |
| execution-fix raw | `benchmarks/artifacts/task037_extra_development/m1_caed4dea_execution_fix_run1`；watchdog `d9a094debc89e37df93a2b4bbc7a1209aa0d07b96d879907673b7d82dd38a9c0` |
| frozen checker negative | `benchmarks/cases/101_task37_extra_development/records/m1_fullspace_p4_p6_transfer.json`；file SHA `ad4184d82743a3063d426ad2bd2c2e582c5c3f6f5d8999548cf2d81d704422b0`；embedded evidence SHA `a6aebc97116ff7d4baf3280d6d705a5fc420ce4f6be15eb9c2bb7582a921774f` |
| current v2 checker | `benchmarks/cases/101_task37_extra_development/records/m1_fullspace_p4_p6_transfer_v2.json`；file SHA `6ed2c394fc0e04ed1222024bb1cc89281d6c77ac9be28e07451312906107cf72`；embedded evidence SHA `2820715b3d30d54ee7af9169884b4cf562fbb969c0be31bb2238304366cf56ba` |
| current v2 raw watchdog | `benchmarks/artifacts/task037_extra_development/m1_cc0573b_qualification_run1/m1_watchdog_summary.json`；SHA `7ffa3c129a7938d4a9a34787b6709c62ba6fec950a236df2a46dfb25b3725389` |
| fixture diagnostics compact | `benchmarks/cases/101_task37_extra_development/records/m1_fixture_diagnostics.json`；由 `evidence_sha256` 自绑定 |
| source fixture diagnostic | `/tmp/task037_m1_floquet_polynomial_probe.json` SHA `7cc3f26392b3f485fc2d9d9971db97b609c0cf0ceff113f7d47ab5e7acf7c09d`；script SHA `44025eeee04644e365a6126643b1f8b95ba39e8e6528d8194b1eff2ceb2582a0` |
| MPC diagnostic | `/tmp/task037_m1_mpc_commutation_diagnostic.json` SHA `3522def9cf00c532b8fc1a2a3839a7837d0a60f01903da7295ef5bccf6e519e0`；script SHA `1bcb35d36717398aa415009462a0de79ec2474ed0b684de630fb8195b60dbeb1` |
| orientation diagnostic | `/tmp/task037_m1_orientation_diagnostic.json` SHA `53e7bf5f60faf01657c8fd88626d510adb24c8b8ab6db7534e8ff897eedf1f76`；临时 JSON 未嵌入 source/script SHA，compact 已标明该 provenance 限制 |
| dual partition diagnostic | `/tmp/task037_m1_dual_partition_diagnostic.json` SHA `954d22b4b40a45afc969af59b28cb3da5d170ddd8c74cd254e91f86a0a045af5`；script SHA `ba8900b97ae869001c7e3a05fd09bf6c626b995433f384a3688e0ee14ebb4ca5` |
| M3Y raw / watchdog | `benchmarks/artifacts/task037_extra_development/m3y_404f6c6_run1`；`m3y_watchdog_summary.json` SHA `bd364d928a45fda15f49c8890c76ea6a59029b6320221cc7ec546b73f32fdeb8` |
| M3Y stage / builder / loader summaries | `stage_summary.json` `250e61783bf97ceb9a74fde8bf52910ad7d4f7d609fdfff852f098a6f814204c`；`m3y_builder_summary.json` `d0d7d3a80384994b3415dc41ac3e1b816c35b6ff0682fd3ad8384bb3a8fcb652`；`m3y_loader_summary.json` `eece84bb7250a80967665a0d63aef91dc9a0bd34366f69e2f506200a1e30ab82` |
| M3Y progress / timeline | builder `5676e6074bdb0a219cc7f96c26ea03071d74b2885e7481cb3633743f8d7aa2af` / `213d8dc29598b3487f2278b684a09eb4174f2f8791dcfe00acaa339f59714512`；loader `da0a2c7aeb10f406357d486af76c6dbc9f89b266dea712044b7f70c732cca2f1` / `80c29993fe52821ec2711c6b1d52e45027289a81f6f8b4b656fc02713410c1a6` |
| M3Y stage progress / timeline / manifest | `1648701c75611f180a0c7d7444584ff25f63f815742f21cbc4a45ed19fe8a60d` / `3d79487825b847a7fd23f67d485c995c0874ff5b1389b1909577913bbcdc0b0a` / manifest `949c04da123ccf1e0014a301f617e3a9509b9aaed365793948c469e12feade17` |
| M3Y compact | `benchmarks/cases/101_task37_extra_development/records/m3y_full_packed_patch_store.json`；file SHA `f40d6e27c628b946f9ff735027e966cd192748322aa29f752f27ebc4daeab979`；embedded evidence SHA `605cb0c19e4e7c49d0304474b1e6844d2047f78abca8d20e7692ba524de5b241` |
| M2 final raw worker | `benchmarks/artifacts/task037_extra_development/m2_b4c1c6c_statm_run1/m2_worker_summary.json`；SHA `3db16f4d2709c9839bbdec88366c0f740da1f7cd871981992c71c758adc74f73` |
| M2 final raw watchdog | `benchmarks/artifacts/task037_extra_development/m2_b4c1c6c_statm_run1/m2_watchdog_summary.json`；SHA `bad3879a32d11434caf2bb5d4c235b05a91ffd7c210a4add496be958fd6d7425` |
| M2 final raw form reuse | `benchmarks/artifacts/task037_extra_development/m2_b4c1c6c_statm_run1/m2_form_reuse.json`；SHA `7f90385c16534e79c81df8b36103c2ddfe52c6afcc7759ef9ec493e2fd1c27e9` |
| M2 v2 compact | `benchmarks/cases/101_task37_extra_development/records/m2_high_complement_patch_oracle_v2.json`；file SHA `ebd512aa0e4b6823d5d95c5f816cc6e898c9fd97392af4f7346c83ba3ac4e31f`；embedded evidence SHA `59e0af2e187be4bc593db25a81b5c685fdbbeac5d45633687ae35863a12843a5` |
| M2 initial negative compact | `benchmarks/cases/101_task37_extra_development/records/m2_high_complement_patch_oracle.json`；SHA `bfb59f5b2f0c75e1863a78cd58bb951f2b3dbd30a7f3b2bd4526f8c77ae57023` |
| M2 BEST_CASE diagnostics | first JSON SHA `7d5e511377801efd4473ae795a6a09ab9394adcf39527d4f799d5dfd6afcde52`；coupled JSON SHA `ad900db41005e3540e4c3088b59145e5991290a71f3e8ca76667c267f9f3485e`；coupled script SHA `e74f8528c25eda0e86acb8754c7705fffb1c7bcb103d59f117fbfa52713ef5fc` |

## M6A full-space matrix-free DtN formal run3

DtN（Dirichlet-to-Neumann）在这里表示：给端口上的场系数，计算相应的端口通量。M6A 只验证这个 80-mode、matrix-free action 在真实 p6/h10 全空间上的实现与独立流式 modal-sum 对照一致；它没有运行时谐 PDE，也没有产生 R/T/A 或最终物理结论。

| 项目 | 正式结果 |
| --- | --- |
| source | `2a9dabaa13365373864814d7146ee9399395ed51` |
| scope | p6/h10、252 cells、173,802 rows、9,210 constraints、nloc=882、80 modes |
| watchdog | RC0，raw status `measurement_complete`，stage→MPI1→MPI2 完成 |
| checker | RC0，`status=pass`、`pass=true`、15/15 checks、`problems=[]` |
| MPI1/MPI2 numeric | candidate/direct action、physical RHS、recovery、repeat 五项误差均 `0.0`，finite |
| cross-MPI | source/action/RHS/recovery/mode manifest checks 全 true；recovery relative error `0.0` |
| retained+work | MPI1 `16,673,350 B`；MPI2 global sum `16,757,900 B` |
| lifecycle | stage/MPI1/MPI2 peak `527,859,712 / 388,956,160 / 693,411,840 B`；swap=0；online compiler descendants `[]`；process cleanup=true |

candidate/direct 均保持 `fine_space=uncondensed_fullspace`，不创建 global/augmented matrix、static condensation、trace slab 或 explicit C/D（count=0）；direct oracle 使用流式两 pass。cache 有 20 个文件，满足 `stage == online before == after == final`。这些是 action/DtN 证据，不是 PDE 或 full-memory evidence；M6B、time-harmonic screen、field/RTA 和最终 `<2GB` PDE 目标仍未运行。

| M6A evidence | 路径 / SHA |
| --- | --- |
| raw tree | `benchmarks/artifacts/task037_extra_development/m6a_2a9daba_run3`；digest `665f3a02a13f73c0a949e817c3b2bc7fc915166c10f61dc844c09a242f7cff52` |
| watchdog | `.../m6a_watchdog_summary.json`；`2a275b43f756a54e8285d0bc16d57947e6731d1615d91ecc37d2295182ffccd6` |
| checker | `benchmarks/artifacts/task037_extra_development/m6a_2a9daba_run3_check.json`；`d121f19553576e1fcce947325edc35c1ef16ecbf370cab9b7ad1477fe16b0c2a` |
| embedded checker evidence | `9a412106a6428c1555b58945eeda6a5b1294bd0e1e85bc763c6c46a7314f30a4` |
| tracked compact | `benchmarks/cases/101_task37_extra_development/records/m6a_fullspace_matrix_free_dtn.json` |

M6A run1 的 online-JIT/cache lifecycle negative 和 run2 的 watchdog-JSON serialization negative 均保留为 execution failures；run3 是修复后的 positive authority，不覆盖旧 raw/check。

## 未运行项与硬停止

M1 v2 已通过；M2 已完成正式运行但因 checkerboard 数值 Gate 失败而 `NOT_QUALIFIED`；M3Y 已由用户明确越锁授权并正式通过；M4Y 已正式运行但因 checkerboard 数值 Gate 失败而 `FORMAL_NUMERIC_FAIL / NOT_QUALIFIED`；M5 第一屏和 M6A action/DtN 已正式通过。M6B/W5 disk screen 已正式运行但为 `NUMERIC_FAIL / NOT_QUALIFIED`；full PDE、official field/RTA、direct-authority physics comparison 和 PDE process-tree RSS 仍为 `not_run_yet`/`not_measured`。75D coarse 的 `not_needed/not_run` 只属于旧 M5 coercive screen 结论，不能外推为当前 time-harmonic W5 不需要 coarse。尚不能声称达成 MPI1 full PDE RSS 严格小于 2,000,000,000 B、swap=0 且直接法物理对照通过的最终目标。

M2 与 M4Y 的数值 Gate 失败均保持原始负结论；用户之后的明确授权已开启 M3Y、M4Y 以及后续 M5/M6 正式研究，但没有把任何失败改写为通过，也没有放宽 Gate。M1/M2/M3Y/M4Y/M5/M6A compact、所有早期执行失败 raw 和 M4Y-W 诊断均保留；没有新分支、PR、master/default 修改。研究代码和历史负结果保留，ordinary default 不变。

## W5 磁盘外置 Krylov 屏幕：资源通过，数值未通过

W5 把 Krylov 基向量放入外部 scratch 文件，避免这些大向量长期占用进程 RSS。这只解决内存占用方式，不改变物理算子，也不等于解决谱收敛问题。

本次正式屏幕的 producer SHA 是
`41cbbd454eb8336d9ea5378ed618447acfc60aac`，checker SHA 是
`9317e19e924e5b15297c168ea4f2271ae42172eb`。独立 checker 结果为 `RC=1`、`classification=NUMERIC_FAIL`；执行证据和资源证据均完整，峰值进程树 RSS 为 `1,607,802,880 B`，swap 为 `0`。

| checkpoint | true relative residual | Gate |
| --- | ---: | --- |
| 20 | `0.3237575899853163` | `<=0.60`，PASS |
| 100 | `0.18105272614044404` | `<=0.20`，PASS |
| 150 | `0.15403613391023072` | 记录值 |
| 200 | `0.12750559935416836` | `<=0.08`，FAIL |
| 150→200 | `0.17223578573793497` | `>=0.15`，PASS |

因此 W5 的 disk-backed 实现通过了资源与证据边界，但没有通过最终屏幕数值 Gate。full PDE、official RTA、direct comparison 和最终 PDE 内存目标仍未运行。用户已明确授权继续研究具体收敛问题，但 2GB/swap、true residual 和 physics Gate 均保持不变；本段不改写任何旧 raw 或历史负结果。
