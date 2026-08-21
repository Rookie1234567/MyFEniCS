# Task038-extra `response_v2`

## 1. 结论

这里的“action”是给定 full-space 向量计算物理算子作用的过程；“transmission”是两 slab 之间交换界面信息的人工边界近似；“authority”是可以把一个历史向量安全解释为当前物理向量的、带 hash 的独立证据；“controlled stop”是 watchdog 按硬资源上限主动停止进程并保留负证据，不等于数值算法失败。

T1–T4 及 Review V2 的 R0–R3 已通过。R1 证明 old W5 与 current 的物理 dual RHS 不是同一向量，R2 建立了 current top-boundary component oracle，R3 通过 current operator 在 historical W5 primal state 上重算了 residual。R4 在 Candidate A 的 physical source 上数值失格；随后 Candidate C 在正式记录生成前触发 12 GiB process-tree hard stop。故本批次结论为：

```text
R4 = FAIL / CONTROLLED_STOP_RESOURCE
R5、T6-S、T6-F、E/H、R/T/A、T7–T9、full 0.7 nm PDE = not_run_by_R4_gate
```

Candidate A 的 physical contraction 失败不是实现缺陷；Candidate B 不是数值失败，而是当前 mixed interior interface 没有合格的 interior modal authority；Candidate C 的 formal 数值字段没有运行到可判定状态。

## 2. Review V2 §8 的逐项回答

### 1. branch、base、Review V2 start、final source、upstream 和 worktree

| identity | value |
|---|---|
| base master / merge-base | `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| Review V2 start HEAD | `e2bff303115362376f2294b71c3f9d131dbfce09` |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| final code/evidence source SHA | `ea7fc96b8c95eca13b5ee8055d7e0762f9ab02dc` |
| upstream before docs closure | `e2bff303115362376f2294b71c3f9d131dbfce09` |
| source relation before this document-only closure | ahead `8` / behind `0` |
| ABI | qualified WSL activation；repo `.venv`；PETSc `complex128` / `int32`；DOLFINx、Basix、mpi4py、petsc4py、slepc4py 同一 Linux ABI |
| threads | OpenMP、OpenBLAS、MKL 均限制为 `1` |

`ea7fc96...` 是本轮代码和 formal evidence 所绑定的 source HEAD。文档内容不能自引用未来 commit；ignored raw、mesh、JIT 和 canonical shard 没有变成 tracked 文件。最终提交/push状态由交付报告给出。

### 2. R0–R5 planned/run/pass/fail/not_run 矩阵

| stage | result | evidence |
|---|---|---|
| R0 identity/ABI/artifact preflight | `PASS` | qualified activation、clean source、old W5 hashes、资源和磁盘核对 |
| R1 old/current identity | `PASS` | `r1_clean_cd1ca8d`；classification=`HISTORICAL_W5_NOT_SAME_PHYSICAL_RHS` |
| R2 current dual component oracle | `PASS` | source `09b926428babc2f0a8dd4b4061b7e18d7dd23aba`；p2/p3 MPI1，p6/h10 MPI1+MPI2 |
| R3 current recomputed residual | `PASS` | source `2c8fca90c7300b85b30021081868b699c0b306d2`；MPI1/MPI2/pair；process-tree resource provenance未测 |
| R4 Candidate A/B/C | `FAIL / CONTROLLED_STOP_RESOURCE` | A physical contraction fail；B not applicable；C 12 GiB hard stop |
| R5 T6-S screen | `not_run_by_R4_gate` | 没有运行 20/100/150/200 checkpoints |

R0–R3 的 `PASS` 是各自 authority/identity Gate 的通过，不表示 R4 sweep 已经收敛。

### 3. old/current physical identity manifest

Current manifest 的必需字段来自实际 resolved `.dat` 路径和 production mode inventory：

| field | current result | old W5 result |
|---|---|---|
| wavelength / degree / target h | `13.5 nm / 6 / 10 nm` | wavelength unavailable；old degree/target contract not independently complete |
| geometry | `252` cells、`420` vertices、axis `[7,4,15]`；geometry SHA `e94ca5e02cf5f3919fde16493ca0ab51d6da97693496b5a9da33d6e433469f0a`；connectivity SHA `d9bc3d6c0ffba47b5a7e6a966f2294607fb91c342b62205f61ae3a558c7f8433` | exact old mesh H5 SHA `ae9755890127023577a4e6b54a6d5b79aec4048a3ccbb48aec6c8c30e891bd13`，XDMF SHA `e40e1b05f3269101fe93e96416481f14bcaa64fb1df5f030381c747b484b9864`；geometry/connectivity witness一致 |
| resolved input | `4076` bytes，SHA `78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad`；template SHA `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` | unavailable |
| material / incident / Floquet | current physical material tags、斜入射、finalized Floquet MPC 可读 | old mandatory epsilon/loss、incident amplitudes、Floquet phase unavailable |
| FE/quadrature/facet normal/tag/measure | current production definition已绑定 | old quadrature、normal/tag、measure unavailable |
| MPC | current rows `173802`、constraints `9210`、relation digest `73920dca3253b238feba530af3c4dd02c34e40b7f0a47d844ce619f4f4765ad6` | old MPC relation digest unavailable |
| ordered modes | current `80`，SHA `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2` | old count `80`，SHA `8d7c396b5251365c6865b2fafefd37e1559794fe39f445ef8bccc3b8ff29cac5`；per-mode `m/n/pol/alpha/gamma/kz/e/traction/H` unavailable |
| current RHS identity | incident top traction + negative modal traction，按显式 `H` 归一化，finalized MPC 一次 | old extractor/source blob存在，但上述 mandatory component semantics 不能独立恢复 |

R1 record 的 source SHA 是 `cd1ca8dfe6fdcc7a526d2794d2963dd6cd81a470`，record SHA 为 `9e828db48bef2b4467c8eaf832791902a4272a78cfa5062b44ac8b1efb4c620f`，checker SHA 为 `3f2232ed14e31c52f02e3ba6d40e5d36519b88899fd8f68081d8f0cbbec14774`。checker 对缺失 old 字段 fail-closed；没有用 current 字段填补 old provenance。

### 4. RHS 的 incident/modal/per-mode/per-component 分解

old/current canonical RHS 各有 `164592` 个 packet，key set 相同，duplicate/missing/extra 为 `0/0/0`，但 relative coefficient L2 为 `10.934736136386151`，最大 packet absolute difference 为 `1.2846616424283923`。差异集中在 top boundary：top dimension-2 old/current norm 为 `13.197393883461924 / 1.325370803357057`，top dimension-1 difference norm 为 `0.013361553097537709`；bottom 为零，side/volume 仅数值零附近。

R2 用 current fresh direct component oracle 检查了 incident base 的 tangential component 0/1、每个 mode、side/polarization grouped totals 及 whole modal total。实际 case 是 p2/h50 MPI1、p3/h50 MPI1、p6/h10 MPI1 和 p6/h10 MPI2；没有补造 p2/p3 MPI2。冻结 mode inventory 为 p2/p3 `88`、p6 `80`；p6 MPI1 最大 candidate/direct relative L2 为 `4.559266389658486e-14`，H 最大相对误差 `3.2741809263825522e-15`，amplitude 最大相对误差 `2.8801676090923355e-15`，all-mode 与 side/polarization recomposition 均为 `0.0`，repeat 最大 `4.8257303460951034e-17`。这证明 current dual component path，不证明 old/current RHS 相同。

### 5. normal、sign、H、conjugation、measure、orientation 和 phase-once

当前路径中，surface normal/tag、negative-traction sign、显式 modal normalization `H`、UFL conjugation、facet measure、Basix orientation 和 finalized-MPC phase-once 均由 R2 independent direct oracle 与 p2/p3 MPI1、p6/h10 MPI1+MPI2 evidence 共同通过。R2 的 production source manifest 绑定了 `dtn_port_3d.py`、`fullspace_dtn_action.py` 和实际 mode manifest，而不是在 checker 中复制公式。

这些证据不能裁决 old W5 的同名字段：old mandatory normal/tag、amplitude、H、orientation、quadrature 和 MPC relation 不可用。因此不能把 old/current 的 top discrepancy 归咎于某一个 sign 或 phase，也没有做 alpha 拟合、符号扫描或容差放宽。安全裁决是：current convention 已通过；old physical dual authority 未建立。

### 6. 是否修改 current numerical core及影响

本轮 Candidate C 生产代码只增加显式 opt-in 的 fixed second-order local impedance，用于 local shell 的人工 transmission；它不改变 exact physical action、Maxwell 弱式、材料、Floquet phase 或 T1–T4 的 ordinary default。Candidate A 默认仍为原路径，A 的正式负证据仍有效。C 的 formal 过程在 worker 写出 record 前因资源 hard stop结束，所以不能把 C 的 192 B class payload、rho 或 closure写成正式通过。

R2/R3 authority 代码已绑定各自 clean source；本次 docs closure 没有改 Python，也没有使既有 T1–T4 数值 evidence 自动失效。

### 7. 修复后 T1–T4 的 fresh evidence

R1–R3 在各自 clean SHA 上进行了 fresh authority evidence：R2 为 p2/p3 MPI1、p6/h10 MPI1+MPI2 component oracle，R3 为 p6/h10 MPI1/MPI2 primal canonical roundtrip、current action/residual closure 和 pair identity。R3 的数值/authority Gate 通过，但只保留 rank-local RSS/VmSwap；process-tree watchdog provenance 未测，因此不宣称 R3 的 process-tree resource qualification。Candidate C commit 后还重跑了 `test279` serial/MPI2、compileall、AST duplicate-key 和 diff-check；Candidate A/C 相关 serial/MPI2 focused regression 也已完成。

没有修改 T2/T3 physical action、dynamic mode 或 T4 default interface semantics，因此没有把 Candidate C 的未完成 formal 当作 T2/T3/T4 的新 formal 结果；已有 T2/T3/T4 formal aggregates 保留其原始 source/evidence SHA 和边界。

### 8. Path A 与 Path B 的 long-tail authority

Path A 被判为 `NOT_QUALIFIED`：old W5 缺少 mandatory physical/Floquet/orientation fields，不能证明 old residual row array 是 current full-space dual。没有拟合或修复 old dual。

Path B 的 source 名称精确为 `CURRENT_RECOMPUTED_RESIDUAL_AT_HISTORICAL_W5_STATE`。它把 old W5 solution（file SHA `d2a5a7e7b94a73d5212bc693d43282cace2883aadd0bb66780a3f8ae7b9e535e`，array SHA `620b5e496536d69c0bc471731b09a15424c29044e6836881ccd85340cbee0c39`，shape `[173802]`，complex128、finite）映射为 current canonical primal state，重建 current p6/h10 physical RHS，用 current volume+dynamic DtN exact action 计算 `r=b-Ax`。MPI1 primal roundtrip 为 `1.3336463445521434e-17`，residual recompute closure 为 `2.381515544959568e-18`，action repeat 为 `0.0`，apply count `2`。R3 source manifest SHA `62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce`。

### 9. old residual、MPI1/MPI2 和 closure

MPI2 只读取 hash-bound MPI1 primal canonical manifest，不读取 old 92 MB residual shard。MPI2 re-extract 后 residual closure 同为 `2.381515544959568e-18`，repeat `0.0`，apply count `2`；MPI1/MPI2 mapped primal relative L2 为 `1.4389898139779045e-17`，residual canonical relative L2 为 `1.145631881739048e-14`，source relative L2 为 `0.0`，duplicate/missing/extra 为 `0/0/0`，swap 为 `0 B`。R3 process-tree resource provenance 未测，以上不是 process-tree resource qualification。

旧 W5 residual file SHA `4166665f2e3c302f0645d9581856ec1bc433de4679540e45f98eb1e161093cc6`、array SHA `35de8f03a1fdf4c410cff33ceee44a31831df418443c7534650308505114de98`；其内部 `rhs-outer_action` closure 为 `1.742722222852365e-20`。old residual norm `1.6827423227554978`，current recomputed residual norm `387.39250373645797`，angle `1.5212340930320511` radians。该比较只是 diagnostic，不能把 old residual当 current authority。

### 10. A/B/C 五类 source、rho、wall、retained 和资源

| source | Candidate A | Candidate B | Candidate C |
|---|---|---|---|
| physical RHS | MPI1 `rho=0.8145890334049838 > 0.60`，closure `1.2458376041083906e-16`，repeat `0.0`，wall `2812.015165732999 s`，process-tree peak `5,145,784,320 B`，swap `0 B`；numeric contraction FAIL | `NOT_APPLICABLE`：没有 interior modal authority | MPI1 在 record 前 resource=`CONTROLLED_STOP_HARD_12_GIB`；rho/closure/repeat not run；wall `406.7977727999969 s`，peak `12,942,209,024 B`，swap `0 B` |
| gradient | MPI1 `rho=0.8889127715646881 <= 0.90`，closure `1.271047984953834e-19`，repeat `0.0`，wall `2747.751835015006 s`，peak `1,323,728,896 B`，swap `0 B`；numeric PASS | `NOT_APPLICABLE` | `not_run_by_R4_gate` |
| curl | `not_run_by_fail_fast` | `NOT_APPLICABLE` | `not_run_by_R4_gate` |
| checkerboard/high-frequency | `not_run_by_fail_fast` | `NOT_APPLICABLE` | `not_run_by_R4_gate` |
| R3 qualified long-tail | `not_run_by_fail_fast` | `NOT_APPLICABLE` | `not_run_by_R4_gate` |

A 的 retained support metadata 为 `3,317,760 B`，fixed-GMRES Arnoldi basis-derived bytes 为 `50,054,976 B`；这两项只对实际运行的 A source 作为 audit telemetry，不是全部 process-tree workspace。A formal 尚未进入 MPI2。C formal class manifest 和 `192 B` retained numeric payload 均为 `not_formally_validated`。

Candidate A 的 physical 与 gradient 两个 watchdog resource gate均通过；A physical 的 contraction Gate失败后按 fail-fast 停止剩余 8 个 case。Candidate C 的 raw watchdog 返回 `-15`、stop reason=`hard_stop_12_gib`、SIGTERM 后无需 SIGKILL；这不是 Candidate C 的数值失败。

### 11. T6-S checkpoint

T6-S 没有运行，因此以下全部是 `not_run_by_R4_gate`：20、100、150、200、final true residual；150→200 improvement；RSS、swap 和 wall。没有用 R4 的 sweep rho 或 KSP monitor 冒充 T6 checkpoint。

### 12. T6-F、E/H、R/T/A、T7–T9 和 0.7 nm 边界

T6-F full solve、official E/H recovery、R/T/A、`A_volume`、diffraction channels、direct comparison、T7 h-scaling、T8 0.7 nm/2 TiB、T9 closeout 和完整 0.7 nm PDE 全部 `not_run_by_R4_gate`。`outcomes/summary.md` 与 `docs/development_progress` 保持 T9 closeout 状态，没有伪造完成。

`<2 GB` 是战略目标而不是本轮已达成的 PDE 结论。A 的两个 action-only process-tree peak 分别为约 `5.145 GB` 和 `1.324 GB`；没有完整 PDE，不能把它们称为 full-solve memory scaling。

### 13. measured、derived、predicted、failed、controlled_stop、not_run

| classification | 本批次内容 |
|---|---|
| measured | T2/T3/T4 action/oracle/repeat/MPI identity；R1/R2/R3 packet facts；A 两个实际 rho、closure、wall、process-tree peak、swap；C watchdog raw/compact resource facts |
| derived | canonical relative L2、R3 roundtrip/pair closure、T2 retained exponent、A retained/support audit、R1 physical classification |
| predicted | 没有用预测值替代任何 Gate；`<2 GB` 仅保留为未验证战略目标 |
| failed | A physical contraction：`0.8145890334049838 > 0.60`；R1 old/current physical RHS equality claim不成立，但它被分类为不同物理，而非代码故障 |
| controlled_stop | C resource=`CONTROLLED_STOP_HARD_12_GIB`；process-tree 达到 12 GiB硬上限，`return=-15`、swap `0 B`、没有 SIGKILL |
| not_run | C 数值 fields、A 其余 8 案、所有 B formal、C 其余 source/MPI、R5、T6及后续 full PDE |

### 14. changed files、tests、checker、rendered view 和 evidence index

本回合只新增/更新 docs 和轻量 compact JSON；没有修改 Python。待交付 docs 文件为：

```text
docs/task038_extra_full3d_iterative_0p7nm/response_v2.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/t5_physical_dual_authority.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/sweep_oracle.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/test_summary.md
docs/development_model_registry.md
docs/task038_extra_full3d_iterative_0p7nm/outcomes/records/t5_*_v2.json
```

R1/R2/R3 checker 均为 read-only、从 raw fields/manifest 独立判定；R4 A individual checker 从 raw vector/action/repeat 与 watchdog 记录判定，未信任 worker status。C 的 checker 命令曾按正式接口执行，但 worker 在写 `record.json` 前被 watchdog停止，因此标准 `check.json` 没有生成；本报告不伪造 checker pass。C 的实际负资源证据是：

| artifact | path | SHA-256 |
|---|---|---|
| watchdog raw | `benchmarks/artifacts/task038_extra_full3d_iterative_r4_formal_v2/ea7fc96/p6_h10_physical_rhs_mpi1/watchdog.raw.json` | `cc1bee361712361af52414e1b0d76bb52fd9712b5eecb01b5375b81d2be23ff0` |
| watchdog compact | `benchmarks/artifacts/task038_extra_full3d_iterative_r4_formal_v2/ea7fc96/p6_h10_physical_rhs_mpi1/watchdog.compact.json` | `3102995f3d10170bb4a96f4890ac9fb919e140c570535a5fd38fb59447179a08` |

Tracked v2 records分别保存 R1 identity、R2 p2/p3 MPI1 与 p6/h10 MPI1+MPI2、R3 long-tail、A、B、C 的 hash-bound compact facts；v1 records 和所有 ignored raw/canonical/mesh/JIT 保留不覆盖。A 的 formal record/check/watchdog hash已写入 `t5_sweep_candidate_a_v2.json`；R2/R3 record/check hash已写入对应 compact。

本地验证包括：T2 `test269/test270` 共 `18 passed`；T3 focused serial/MPI2；T4 `test272/test273` 与相关 MPI2；T5/R2/R3 focused `test274/test275`；R4 Candidate C `test279` serial/MPI2及相关 regression；九份 T5 JSON parse、Markdown fence/table/link检查、`test_26` `14 passed`、compileall、AST duplicate-key、`git diff --check`。这些都是本地结果，不是 CI；本回合不重跑 PDE。

没有做 rendered-view 图像检查；本次交付物是 Markdown 和 JSON，已做文本 fence/table/link 基本检查。

### 15. 下一轮授权建议

本轮不应授权 T6-F，也不应以“C 没有数值 rho”解释为通过。下一步的唯一前置是解释并修复 Candidate C p6/h10 的 JIT/process lifecycle 资源 hard stop，在新 clean source 上由新的 review 重新授权；不能通过预热、拆分 watchdog、降低采样或绕过 6 GB/12 GiB Gate制造伪 pass。只有 R4 全部 source/MPI contraction 和 resource Gate真实通过后，才可以请求 T6-S；T6-F、official E/H 与 0.7 nm arbitrary-3D blocker仍需另外授权。

## 3. 全批次 source/evidence 索引

| stage | source SHA | evidence/aggregate |
|---|---|---|
| T1 | `a18df1ac5e9c9f9c67245a4d33546925c4076aa1` | input contract evidence |
| T2 | `6d60bb5a9a59e88da98b027efeed8506d5dd7a82` | evidence `e4ea540078c4e86dfa0e5762d9dbf241a5c3a728`；aggregate `1b604df72dcaa20a7d23efc1a8dccf3e9564820bbdbf8ad54007f1c6869a7dcd` |
| T3 | `691ac261fd62258d356183cb3c0383307605b15e` | evidence `c44e6a19ee0955988bff3f6110d576cb4cc1fa09`；aggregate `f8fc4947c18d96120057dfefe5a286dc330ce0d3a30d3ff6f74b5d5e33aa6131` |
| T4 | `88e5cef8a007445270721b9076b0c33453f743f3` | evidence `a6a8ca7fea3f071e1769f58f38da3ff95f2577e3`；aggregate `c6f160facd0d843078788fd65c655aba3517d4f70017e3c003d58d8525ce5eb7` |
| R1 | `cd1ca8dfe6fdcc7a526d2794d2963dd6cd81a470` | current identity `563324e8f066beef403cff054f8b72abc5df3973ee2aa6983b245823c49aca37`；old identity `4d396ee6e7069aca9704f86a9ebe813ef8f9fe9846da5c8b8c7e1e70cc200ad5` |
| R2 | `09b926428babc2f0a8dd4b4061b7e18d7dd23aba` | p2/p3 MPI1、p6/h10 MPI1+MPI2 records/checks in `t5_component_oracle_*_v2.json` |
| R3 | `2c8fca90c7300b85b30021081868b699c0b306d2` | residual manifest `62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce`；pair check `891319892e78efdd8c194641ca11d921211bb6506e1dc17b0b60c863cc5f11fd`；process-tree provenance未测 |
| R4 code/formal source | `ea7fc96b8c95eca13b5ee8055d7e0762f9ab02dc` | A formal source was `1a4d495a4f7a78bafb389ab9b30d0b49fe7bd5be`；C watchdog raw/compact listed above |

The document content cannot self-reference its future commit. The final commit/push state will be given in the delivery report.
