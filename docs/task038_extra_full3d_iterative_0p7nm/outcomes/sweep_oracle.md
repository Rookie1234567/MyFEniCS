# Task038-extra T4 sweep/oracle evidence

## 1. 作用与边界

T4 验证的是两层三维子域之间的传输边界动作：给定一个有限元场，candidate A 在真实 interior facets 上施加切向一阶 Robin/impedance 弱式，并把结果传回 owner-local trace。它验证数据限制/延拓、Floquet 约束和传输动作是否一致；它不是 Maxwell PDE 求解，也没有 KSP、全局界面矩阵、dense Schur 或 slab factor。

每个 case 使用同一非平凡斜入射方向（theta=21.131°, phi=33.690°）的固定 s/p 两个解析源，测试场是固定的 `0.6+0.1i` s 与 `0.35-0.2i` p 线性组合。独立 oracle 用 fresh scalar facet quadrature pairing 检查 candidate output；checker 只读取 record/raw manifest，不导入或执行 runner、solver、PETSc、MPI。

## 2. Provenance 与正式 case

| item | value |
|---|---|
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| upstream | `80c3fa29d54813d0344a93ffa7768108ff15fa76` |
| T4 implementation SHA | `8560488d9bafbd608f9dc7c419815f9a632d46af` |
| T4 evidence-fix SHA used for formal v2 | `88e5cef8a007445270721b9076b0c33453f743f3` |
| branch relation at v2 formal | ahead 11 / behind 0 |
| expected/start/end SHA in every v2 record | `88e5cef8a007445270721b9076b0c33453f743f3` |
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| profile | `full3d_scalable_v1` |
| slab count | 2 |
| transmission | `first_order_impedance_robin_v1` |
| official physics | not run |

正式输入是四个冻结组合：p2/MPI1、p2/MPI2、p3/MPI1、p3/MPI2，mesh target 为 50 nm。四次 runner 均使用新的 ignored 根目录 `benchmarks/artifacts/task038_extra_full3d_iterative_t4_formal_v2/`；tracked evidence 只在四次 runner、checker 和 aggregate 全部通过后生成。

## 3. Formal 数值与资源结果

| case | runner wall | global/local facets | owned trace rows | max oracle relative error | R/P adjoint | reconstruction max | warm RSS span | swap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| p2 MPI1 | 1.64 s | 6 / 6 | 48 | `8.6902e-16` | 0 | 0 | 1,409,024 B | 0 B |
| p2 MPI2 | 9.00 s | 6 / 6 | 48 | `5.1927e-16` | 0 | 0 | 1,363,968 B | 0 B |
| p3 MPI1 | 2.13 s | 6 / 6 | 108 | `9.6792e-16` | 0 | 0 | 1,683,456 B | 0 B |
| p3 MPI2 | 9.17 s | 6 / 6 | 108 | `1.1347e-15` | 0 | 0 | 1,667,072 B | 0 B |

每个 case 有两个 source、两个方向、两个 repeat，共 8 次真实 apply；每次 apply 后记录 elapsed、rank-max current self RSS 和当前进程 `VmSwap`。所有 repeat relative differences 为 0。四个独立 checker 均为 `T4_PASS`，aggregate 为 `T4_AGGREGATE_PASS`，精确包含四个 case。

两种 degree 的 topology canonical digest 分别为：p2 `8a325f1de93fbe250235b4a89280007f6bb51a51d9deda80f0698344633f9afa`，p3 `1c60a381f4b5e807328bc5f7c82622f4bff535a1bc260ba0d8fed3046bf97512`。MPI1/MPI2 的 source 和四组 action physical packet key identity 均相同；aggregate 的最大 cross-MPI relative L2 为 `7.1149e-15`，限值 `1e-12`。四组均报告 homogeneous 与 nonhomogeneous interface classes、nontrivial Floquet phases、`finalized_floquet_mpc_once`、slave-row exclusion 和 owner closure。

## 4. Retained payload 与 bounded work

| degree / MPI | retained numeric bytes (local / global-max) | bounded temporary work per apply |
|---|---:|---:|
| p2 / 1 | 45,696 / 45,696 B | 10,368 B |
| p2 / 2 | 30,192 / 30,624 B | 10,368 B |
| p3 / 1 | 127,296 / 127,296 B | 27,648 B |
| p3 / 2 | 84,936 / 85,968 B | 27,648 B |

forward/backward 的数值 payload 与 work 均分别记录在 compact record 中。所有 forbidden materialization audit 均为 false：numeric allgather、global AIJ、dense interface mass/Schur、slab factor 均未发生。process-tree peak 明确为 `not_measured_t4`，不能从这些 rank-local RSS samples 推导 process-tree 峰值。

## 5. v1 负证据与 v2 修复

v1 使用 implementation SHA `8560488d9bafbd608f9dc7c419815f9a632d46af` 的 p2/MPI1 record 首次 checker 失败。真实 pairing 已通过（最大 `8.6902e-16`），但 runner 没有把首个 action output manifest 登记到 `artifacts[source_direction]`，checker 因此拒绝 evidence registry closure。该负结果没有被覆盖或删除：

- [`t4_p2_h50_mpi1_v1_evidence_defect_record.json`](records/t4_p2_h50_mpi1_v1_evidence_defect_record.json)，SHA `b562a70f225d849243a7d82b02d237484518632ed1891eb5efc5beb7d4e71682`
- [`t4_p2_h50_mpi1_v1_evidence_defect_check.json`](records/t4_p2_h50_mpi1_v1_evidence_defect_check.json)，SHA `0195869f2f787ee72949e6ef013114ecc3e8fc2db351c1336743c768e917e308`

Review V1 允许的唯一窄修只增加了该 registry assignment 和对应 contract；没有改变 action、oracle、source、mesh、MPC、apply、packing 或数值路径。v2 以新 SHA 重新完成全部四 case 后才取得资格结果。

## 6. Tracked evidence index

- [`t4_p2_h50_mpi1_v2.json`](records/t4_p2_h50_mpi1_v2.json)
- [`t4_p2_h50_mpi2_v2.json`](records/t4_p2_h50_mpi2_v2.json)
- [`t4_p3_h50_mpi1_v2.json`](records/t4_p3_h50_mpi1_v2.json)
- [`t4_p3_h50_mpi2_v2.json`](records/t4_p3_h50_mpi2_v2.json)
- [`t4_aggregate_check_v2.json`](records/t4_aggregate_check_v2.json)，SHA `c6f160facd0d843078788fd65c655aba3517d4f70017e3c003d58d8525ce5eb7`

所有 raw vectors、canonical shards、mesh/JIT files 与 console logs 仍留在 ignored artifact 根目录；T5 仅完成一次 MPI1 authority 尝试并按 hard Gate 停止，没有运行 T6、KSP、PDE 或 push。

## 7. T5 long-tail authority bridge（MPI1 hard stop）

### 7.1 结论与边界

T5 的第一步不是把旧 W5 的残差直接喂给当前算子，而是先证明旧数组中的每个系数仍代表当前算子所需的同一个物理 dual/load。该 bridge 没有通过，因此状态严格记为 `BLOCKED_BY_LONG_TAIL_RESIDUAL_AUTHORITY`。这不是当前算法的性能失败，也不是残差收敛失败：残差 action、MPI2、Candidate A/B/C 和 T6 均因前置 Gate 未通过而没有运行。

| item | result |
|---|---|
| T1–T4 | PASS（沿用已审查的 compact evidence） |
| T5 MPI1 authority | `BLOCKED_BY_LONG_TAIL_RESIDUAL_AUTHORITY` |
| old/current packet count | 164,592 / 164,592 |
| key set / duplicate / missing / extra | equal / 0 / 0 / 0 |
| actual RHS relative difference | `10.934736136386151`（limit `1e-12`） |
| maximum packet absolute difference | `1.2846616424283923` |
| resource | measured pass; process-tree peak RSS `981,893,120 B`; swap `0 B` |
| residual action / MPI2 / A–B–C / T6 | `not_run_by_gate` |
| T7–T9 / 0.7 nm | `not_run` |

### 7.2 身份、旧 W5 闭合与证据

正式尝试开始时 branch 为 `codex/20260820-task38-extra-full3d-iterative-0p7nm`，Review V1 authority/upstream 为 `80c3fa29d54813d0344a93ffa7768108ff15fa76`，T5 clean source SHA 为 `e97db3680ee501350cc40dabe3b0b01d4c756651`，ahead/behind 为 `14/0`。record 的 expected/start/end SHA 均为该值，tracked worktree start/end 均 clean。Review identity 是上述 V1 authority；文档内容不能自引用未来 commit，最终提交/push状态由交付报告给出。

旧 W5 的 provenance 保留如下：old source `41cbbd454eb8336d9ea5378ed618447acfc60aac`；exact mesh H5/XDMF SHA 分别为 `ae9755890127023577a4e6b54a6d5b79aec4048a3ccbb48aec6c8c30e891bd13` 与 `e40e1b05f3269101fe93e96416481f14bcaa64fb1df5f030381c747b484b9864`；old RHS file/array SHA 为 `caf87001775247cb6967d6ebb244c8eb646bcd0d71c6e77410cd091488b1b87f` / `31384363d498673ab5e30a26d47042581756ecabfc0efe3dba7a956b3600c20f`；residual file/array SHA 为 `4166665f2e3c302f0645d9581856ec1bc433de4679540e45f98eb1e161093cc6` / `35de8f03a1fdf4c410cff33ceee44a31831df418443c7534650308505114de98`；outer action SHA `f2605312bf172f91ad13d3a9855ed006b87419be9392f6dbef24c17b51b41de2`；solution SHA `d2a5a7e7b94a73d5212bc693d43282cace2883aadd0bb66780a3f8ae7b9e535e`。旧数组均为 shape `[173802]`、`complex128`，并且 `rhs - outer_action` 重现 residual，relative L2 为 `1.742722222852365e-20`。这些事实证明旧 W5 文件内部闭合，但不自动证明旧系数在当前物理 dual convention 下仍可用。

compact evidence：

- [`t5_mpi1_authority_v1_record.json`](records/t5_mpi1_authority_v1_record.json)，SHA `ec91c5652580bcd6f922c58ee1741ae7b7063dedf9e531d24f701c5bdfa28dd1`；
- [`t5_mpi1_authority_v1_checker.json`](records/t5_mpi1_authority_v1_checker.json)，SHA `ddafbabc9e5e120a09919b5db73ae644adccac8974f54368c9c42251deab8b8b`；
- [`t5_mpi1_authority_v1_watchdog.json`](records/t5_mpi1_authority_v1_watchdog.json)，SHA `226dd35e661e4d00c05c438aab8f6f0cacdc74300e605bb4ab3f9689d0de1ece`；
- [`t5_mpi1_authority_v1_rhs_diagnostic.json`](records/t5_mpi1_authority_v1_rhs_diagnostic.json)，SHA `c4dad79358212d2440a9b66aee99861eb8170eb3ca03ae6f29d368aac2ef5237`，保存本节的 packet/norm/alpha/位置分组和 composition provenance。

92 MB old shard、raw vectors、mesh/JIT 文件、watchdog raw 和日志仍只在 ignored `benchmarks/artifacts/task038_extra_full3d_iterative_t5_authority_v1/mpi1/` 下；Git 只保留上述 compact JSON。

### 7.3 只读数值诊断

从 old/current canonical packets 流式计算，令

`alpha = argmin_a ||current - a * old||_2 = sum(conj(old) * current) / sum(|old|^2)`。

| quantity | value |
|---|---:|
| old norm | `13.197399418369045` |
| current norm | `1.3253714387502278` |
| `||current-old||_2` | `14.492586965436216` |
| relative difference to current | `10.934736136386151` |
| best complex alpha | `-0.09791253215983536 - 0.019929962676216016 i` |
| `||current-alpha old||_2` | `0.13293210647187068` |
| scaled residual / current norm | `0.10029800143967213` |

159,408 packets in each side are exactly zero and all packets are finite. The nonzero discrepancy is concentrated at the top boundary: dimension-2 top packets have old/current norms `13.197393883461924` / `1.325370803357057` and difference norm `14.492580806041088`; dimension-1 top packets have norms `0.01208688253469283` / `0.0012977917853108228`. Bottom packets are zero, while side/volume groups are at approximately `1e-12` or below. This is a value mismatch in the physical load, not a key/order/partition mismatch.

“Key 完全一致”只说明两个文件把同一批物理实体（以及相同的 packet 数量和去重结果）排列在同一组 canonical keys 上；它不说明这些实体上的 dual/load 系数相同。残差是要施加给当前算子的物理 covector。如果 key 相同而 value 不同，直接搬运 old row array 会把另一个物理 forcing 当成当前 residual，因而不能安全进入 action 或 MPI2 reconstruction。这里即使允许一个全局复数缩放，缩放后的相对残差仍为 `0.10029800143967213`，所以不能用一个整体相位或幅值解释掉差异。

### 7.4 old/current composition 能证明什么

只读源审计显示 old `benchmarks/run_task037_extra_m6b.py` 走 `compose_m6b_physical_rhs -> dtn_action.compose_physical_rhs`，current `benchmarks/run_task038_full3d_t5.py` 走 `FullspacePhysicalAction.compose_physical_rhs -> dtn_action.compose_physical_rhs`。两条路径名义上都是 `target = base incident traction + modal coupling`；两者都使用 `_incident_top_traction_form`、`_incident_projection_onto_top_mode`，并且 coupling carrier 都采用 negative traction convention。exact mesh geometry/connectivity witness、packet key/count 和 duplicate 结果也一致。

但现有证据不能证明 current MPC-aware surface assembler 的 component coefficients 与 old exact-component entries 数值相同，也不能证明两次 dual extraction 的物理 covector normalization、orientation transform 和 measure 语义相同。旧 RHS 中大量零值更增加了这个风险：row SHA 或总体 shape 相同并不能替代非零 top modal load 的物理 witness。因此没有猜测 sign 或 normalization 根因，也没有修改数值代码；旧 W5 的负结论保留为历史证据，不能解释为当前算法性能失败。

### 7.5 资源和后续硬停止

外部 watchdog 返回 code `0`，wall `34.103594134998275 s`，sample count `35`，process-tree peak RSS `981,893,120 B`，memory authority peak 同值，process-tree swap 与 dedicated cgroup swap 均为 `0 B`；没有 stop reason，也没有 SIGKILL。该资源 Gate 是实测通过，但不解除 RHS bridge hard stop。

因 bridge 未通过，residual source/action/repeat/reference canonical packets、residual action/reference checker、MPI1→MPI2 residual roundtrip、MPI2 authority、Candidate A/B/C sweep 和 T6 都是 `not_run_by_gate`。本轮不把未运行项写成通过，也不启动 T7–T9 或 0.7 nm PDE。

## 8. Review V2 R4：Candidate A/B/C

这里的 sweep 是把两个 z-slab 依次解一次，再把每个 slab 对当前精确物理算子的作用传播给邻侧，最后用 `r_new = b - A_delta` 检查一次真实残差。它不是把 T4 的单次 Robin 边界动作当成完整求解器。R4 的 contraction `rho` 是 `||r_new||/||r||`，阈值在任何 source 运行前冻结：physical `0.60`、qualified long-tail `0.70`、checkerboard `0.75`、gradient/curl `0.90`。

### 8.1 Candidate A：已完成的两例与 fail-fast

Candidate A formal source SHA 为 `1a4d495a4f7a78bafb389ab9b30d0b49fe7bd5be`。两例都使用 exact current action closure、固定 2 slabs、forward `[0,1]`、backward `[1,0]`、每 sweep 5 次 exact update、fixed local GMRES 8/8、PoU correction；资源由外部 process-tree watchdog 实测。

| case | rho / limit | fresh `b-A_delta` closure | repeat | process-tree peak | wall | swap | status |
|---|---:|---:|---:|---:|---:|---:|---|
| physical_rhs MPI1 | `0.8145890334049838 / 0.60` | `1.2458376041083906e-16` | `0` | `5,145,784,320 B` | `2812.015165732999 s` | `0 B` | `FAIL`，仅 contraction 越界 |
| gradient MPI1 | `0.8889127715646881 / 0.90` | `1.271047984953834e-19` | `0` | `1,323,728,896 B` | `2747.751835015006 s` | `0 B` | `PASS` |

closure、repeat、finite、operator audit 和资源在 physical case 均通过；因此 physical 的负结果是 Candidate A 的数值 contraction 结果，不是 runner/implementation defect。按照 hard Gate fail-fast，以下 8 项没有启动：

```text
curl MPI1
checkerboard MPI1
r3_qualified_long_tail MPI1
physical_rhs MPI2
gradient MPI2
curl MPI2
checkerboard MPI2
r3_qualified_long_tail MPI2
```

A 的两个 compact evidence 记录为 `records/t5_sweep_candidate_a_v2.json`；其中 raw/check/watchdog 的 SHA 指向 ignored 根目录
`benchmarks/artifacts/task038_extra_full3d_iterative_r4_formal_v1/1a4d495a/`。A 的 retained support metadata 为 `3,317,760 B`，fixed GMRES 字段 `50,054,976 B` 只表示 Arnoldi basis derived bytes，其余 KSP workspace由 process-tree watchdog测量。

### 8.2 Candidate B：不适用，不是数值失败

B 的结论是
`NOT_APPLICABLE / CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED`。当前 `interface_z` 是 mixed Si–Si / Si–air interior interface；T3 authority 只覆盖 exterior top/bottom dynamic DtN。没有把全局 Floquet modes 截到零散 homogeneous facets 后冒充 interior modal oracle，因此 B 没有运行 rho、MPI 或资源 formal，也不能写成“B 数值失败”。

### 8.3 Candidate C：focused pass，formal resource controlled stop

Candidate C 是 fixed second-order local impedance；它改变的是人工 PC transmission，不改变 exact physical action、Maxwell 弱式、材料或 Floquet phase。focused authority/tests 已通过，但唯一正式 C case（p6/h10 physical_rhs MPI1，source SHA `ea7fc96b8c95eca13b5ee8055d7e0762f9ab02dc`）在 worker 写 record 前由 watchdog 停止：

| resource field | measured value |
|---|---:|
| wall | `406.7977727999969 s` |
| process-tree peak RSS | `12,942,209,024 B` |
| decimal 6 GB Gate | failed |
| hard 12 GiB Gate | failed (`12,884,901,888 B`) |
| process-tree/dedicated-authority swap | `0 B` |
| return / stop | `-15` / `hard_stop_12_gib` |
| termination | SIGTERM；`sigkill_required=false` |

ignored raw watchdog：

- raw SHA `cc1bee361712361af52414e1b0d76bb52fd9712b5eecb01b5375b81d2be23ff0`，路径 `benchmarks/artifacts/task038_extra_full3d_iterative_r4_formal_v2/ea7fc96/p6_h10_physical_rhs_mpi1/watchdog.raw.json`；
- compact SHA `3102995f3d10170bb4a96f4890ac9fb919e140c570535a5fd38fb59447179a08`，同目录 `watchdog.compact.json`。

没有 `record.json`，所以 R4 checker 的调用按缺失 record fail-closed，未产生 `check.json`。C 的 rho、closure、repeat、finite、update count、class manifest 和 formal retained payload 全部是 `not_run_by_resource_hard_stop`；不能称 C 数值失败，也不能称 192 B payload 已正式验证。

### 8.4 R4 总结与后续边界

| item | status |
|---|---|
| Candidate A | physical contraction fail-fast；gradient pass；不是实现失败 |
| Candidate B | `NOT_APPLICABLE / CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED` |
| Candidate C | `CONTROLLED_STOP_HARD_12_GIB`，12 GiB watchdog hard stop |
| R4 overall | `FAIL / CONTROLLED_STOP_RESOURCE` |
| R5/T6-S | `not_run_by_R4_gate` |
| T6-F/EH/RTA/T7–T9/full 0.7 nm | `not_run` |

`<2 GB` strategic target 尚未达到；A 的 cold peak 和 gradient 的 warm-like peak 不是完整 PDE 内存证明。下一轮必须先解决 C 的 p6 JIT/process lifecycle hard stop并获得新 Review 授权；不得用预热或绕过 watchdog制造伪 pass。旧 T4/T5 sections、v1 negative evidence和 ignored raw 均保留。
