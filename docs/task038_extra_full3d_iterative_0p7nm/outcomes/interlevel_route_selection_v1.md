# Review V12：interlevel route selection v1（截至 R4.2）

## 当前结论

R0 的合同、阈值和历史证据仍然冻结。R3 Route B 结构资格通过后，R4.2 已完成一次 p6/h10/MPI1 setup-only 资源与生命周期审计；离线 checker-v2 判为 `SETUP_EVIDENCE_PASS`，可进入 R4.3 四类 positive，但这不是 solver 或 PDE 通过，也不改变任何旧负结果。

| 项目 | 截至 R4.2 的状态 | 边界 |
| --- | --- | --- |
| R0 contract freeze | `CONTRACT_READY / measured-not-run` | 保留 R0 规则；不代表任何路线通过 |
| Route A：p6→p3 固定谱审计 | `CLOSED_BY_INTERLEVEL_SPECTRAL_GATE` | 首次 shape-contract invalid 与修正后的有效 checker 结论均保留；唯一真实 Gate 是 gradient global adjoint |
| Route B v1 | `CONTRACT_INVALID` | canonical watchdog command mismatch 与 p21 compact NNZ authority 缺失；不重分类 |
| Route B v2 | `STRUCTURALLY_QUALIFIED` | 可进入 R4 审核边界；不是 positive solver pass |
| 当前 route_B | `STRUCTURALLY_QUALIFIED_FOR_R4` | `selected_hierarchy=NOT_SELECTED` |
| Route C | `not_run_by_gate` | 未进入 |
| R4.2 Route-B setup | `SETUP_EVIDENCE_PASS / resource-qualified-for-R4.3` | 仅 setup、10 次 apply、资源与生命周期；不是 solver/PDE pass |
| R4.3 四类 positive | `authorized_pending / not_run` | R4.2 已放行；random/gradient/curl/checkerboard 尚未运行 |
| R5–R7 | `not_run_by_gate` | Route B 尚未失败，Route C 未进入 |
| R8–R12 | `not_run_by_gate` | 需 R4 positive hierarchy 通过后条件进入 |

## 这份合同要解决什么问题

不同阶次的网格之间，不能只凭“局部 transfer 能运行”就宣称它们代表同一个能量空间。Route A 将来会把 coarse p3 空间通过固定的隐式 transfer 放到 fine p6 空间，再比较两个离散算子的能量。直观地说，它检查的是：同一个 coarse 向量搬到 fine 网格后，能量是否仍在预先冻结的范围内。

```math
G_{63}=P_{63}^{H}B_6P_{63},\qquad
q(x)=\frac{(P_{63}x)^H B_6(P_{63}x)}{x^H B_3x}.
```

R0 只固定定义和门槛；没有填写任何 `q`、特征值或 rank 的实测值。

## Route A 的冻结 Gate

| Gate | 固定要求 |
| --- | --- |
| local dimension/rank | `rank = 144` |
| Hermitian defect | `B3` 与 `G63` 各自 `<= 1e-12` |
| strict SPD | `B3`、`G63` 均必须为严格正定 |
| endpoint residual | 最小、最大 generalized eigenpair 的显式 residual 均 `<= 1e-10` |
| endpoint interval | `lambda_min >= 0.10`，`lambda_max <= 10.0` |
| condition | `lambda_max/lambda_min <= 100` |
| global probes | 固定至少 6 个 owner probes；每个 `q` 必须在 `[0.10, 10.0]` |
| operator legality | adjoint、linearity、repeat、finite、input unchanged、phase exactly once 均需独立事实并通过 |

六个 probe 的固定身份和顺序是：`random`、`gradient`、`curl`、`checkerboard`、`physical_component_derived`、`r3_long_tail_derived`；后两个分别对应 Review 文本中的 physical-component-derived 与 R3-long-tail-derived。它们在 R0 只是合同名称，尚未生成数值。R0 checker 只冻结并检查未来 raw scalar facts 的形状和边界；R1 正式 checker 才必须从正式 raw evidence 独立重算可导出的能量比。

每个 material class 在 R1 必须提供以下字段；R0 只把字段名冻结为 schema descriptor：

| material-class required field | 含义 |
| --- | --- |
| `class_digest` | class 身份摘要 |
| `material_coefficient_identity` | 材料/系数身份 |
| `geometry_jacobian_identity` | 几何/Jacobian 身份 |
| `rank`, `sigma_min`, `sigma_max` | 局部维数与奇异值端点 |
| `hermitian_defect_b3`, `hermitian_defect_g63` | 两个 Hermitian 缺陷 |
| `minimum_eigenvalue_b3`, `minimum_eigenvalue_g63` | 两个 SPD 最小特征值 |
| `lambda_min`, `lambda_max`, `spectral_condition` | 广义谱端点与 condition |
| `endpoint_residual_min`, `endpoint_residual_max` | 两端显式 residual |
| `finite` | 有限性事实 |

Route A 失败时，冻结 A 的失败事实并按顺序考虑 Route B；Route A 全部通过时，下一步只能是 R2。R0 不实现这两个后续动作，也不预填它们的结果。

## 截至 R3 的权威状态

下面的状态是对 R0 合同的追加冻结，不覆盖任何旧 record/checker。Route B 的“结构资格”只表示 transfer、局部谱和 owner-packet 证据闭合，不能被理解为已经完成 PDE、长 Krylov 或正定求解器资格。

### Route A：已关闭的 p6→p3 路线

正式 raw source SHA 为 `083869115abe398288360b034bb9762c90838437`。第一次 checker 的 shape-contract invalid 原样保留；修正 shape authority 后的有效 checker 结论为 `CLOSED_BY_INTERLEVEL_SPECTRAL_GATE`，不能把前者删除或把后者改成通过。

| Route A 事实 | 实测值/状态 |
| --- | --- |
| material classes | 10 个；class/inventory 证据完整 |
| process-tree peak / swap | `1,397,800,960 B` / `0 B`，资源通过 |
| 唯一真实数值 Gate | gradient global adjoint `2.8964367576123248e-11 > 1e-12` |
| 结论 | `CLOSED_BY_INTERLEVEL_SPECTRAL_GATE` |

这次失败不是资源失败，也没有重分类 V11 S5。V11 S5 的 6→3 exact-energy negative 仍永久为 `0.04115402900674629 > 1e-9`；3→1 的 `2.7851655955739857e-15` 仍只是同一旧审计中的通过项。

### Route B v1：保留的无效尝试

Route B v1 的两个 tracked compact record/checker 保持 `CONTRACT_INVALID`。原因是 canonical watchdog command mismatch，以及 p21 compact 中缺少实际 NNZ authority。该次尝试观察到的普通 `np.vdot` gradient raw diagnostic 为 `1.2478518260614706e-11`；它只属于这个 invalid attempt，不能当作 Route B v2 结论，也没有放宽任何 Gate。

### Route B v2：结构资格通过

Route B v2 使用 source SHA `91e27ebb4bdcf9de302c12cc5a19ae8eaa78b8c1`，candidate 为 `lor_edge_geometric_mg_6_2_1_nested_v1`，levels 为 `6→2→1`，pairs 为 `6→2` 与 `2→1`。独立 checker 结论为 `STRUCTURALLY_QUALIFIED`，所有 contract、spectral 和 lifecycle errors/gates 为空。

| 项目 | Route B v2 实测摘要 |
| --- | --- |
| exact material classes | `10/10`，全部 rank `54`，覆盖 air/substrate/grating |
| lambda min / max | `0.9999999999999957–0.9999999999999972` / `1.0000000000000022–1.0000000000000036` |
| spectral condition | `1.0000000000000056–1.000000000000007` |
| endpoint residual | 最大 `3.899736900063366e-15` |
| nested energy relative | `3.432582537434375e-16–4.326247611440155e-16` |
| 6→2 local map | edge `882×54`, NNZ `2178`；node `343×27`，NNZ `1331` |
| 2→1 local map | edge `54×12`，NNZ `96`；node `27×8`，NNZ `216` |
| 6→2 local identities | line `1.3088791445326982e-16`、curl `3.938121244967759e-16`、gradient `5.659676773682285e-17`、adjoint `1.7761352040861508e-15` |
| 2→1 local identities | line `3.0764064324107323e-16`、curl `6.976907435801284e-16`、gradient `1.0759403332071913e-15`、adjoint `1.0777112852233726e-16` |
| global probes | 固定六源的 `q` 范围 `0.9999999999999725–1.000000000000014`；最大 adjoint relative `2.1526744277731597e-13`；最大 energy relative `2.7628585938262692e-14`；repeat `0` |
| owner probe | adjoint `2.625232868301171e-18`、linearity `1.2732475304017576e-16`、repeat `0` |
| watchdog | peak `1,294,950,400 B`、swap `0 B`、natural exit、no orphan |

六个 global probe 的固定顺序仍为 `random`、`gradient`、`curl`、`checkerboard`、`physical_component_derived`、`r3_long_tail_derived`；所有 probe finite、input unchanged、phase-once、linearity 和 repeat 事实均通过。R3 long-tail 输入绑定 manifest SHA `62c7824e1032b1a14078d158b0e403b9087dc862bf00386fdce08535e4d76dce`。

Route B v2 的正式 record/checker 为：

- `outcomes/records/lor_edge_geometric_mg_r3_route_b_v2.json`，SHA256 `4c3f9f23f22bc9e20cef8992d99db86f8eda159951b78b016685214bbc274b68`；
- `outcomes/records/lor_edge_geometric_mg_r3_route_b_v2_checker.json`，SHA256 `c48b91a1d6d395e52707a7b680f0227ef4794cfaf1589af8a9ea9627c466fadf`。

ignored artifact root 为 `benchmarks/artifacts/task038_extra_full3d_interlevel_spectral_r3_route_b_v2/91e27ebb4bdcf9de302c12cc5a19ae8eaa78b8c1/p6-h10-mpi1/`。其中 watchdog raw/compact/log/worker NPZ 的 SHA256 依次为：`e876c42e83472ab0bed998d185c3629c661a8b285ce93c9f192f8b3a4f0456a2`、`bec9aae08b5b2a2bb130ddc1ba4d198062b5d753dd020880084e1fe2dca511d4`、`e13d3496e6c68adc8c838ae47c80689f1a716220c99dd628ff91ca9a66045be9`、`7296bac69bb8a46a878661a86e18eac99f5246e6eda71a5b28e5dbe7fdd2fa8c`。

`current route_B=STRUCTURALLY_QUALIFIED_FOR_R4` 只表示满足进入 R4 审阅的结构前置条件；`selected_hierarchy=NOT_SELECTED`。R4.2 setup 已为 `SETUP_EVIDENCE_PASS / resource-qualified-for-R4.3`，R4.3 四类 positive 为 `authorized_pending / not_run`；R5–R7 和 R8–R12 为 `not_run_by_gate`，Route C 未进入。尚未运行四类最终求解，因此不能写成 `POSITIVE_AUXILIARY_PASS` 或 solver/PDE pass。

Route B 的 compensated summation 只用于 Route B 内积归约，固定 `1e-11` adjoint Gate 没有放宽；Route A 仍使用原 `np.vdot` 测量语义。

### R4.2：Route-B setup-only evidence

R4.2 只验证三层层次结构能否完成 setup、固定 10 次 PC apply、资源观测和有序销毁；它没有运行四类 positive source、solver 或 PDE。

第一次 setup formal 的 worker 自然退出，资源事实本身没有越过 hard line，但 checker-v1 永久保留为 `CONTRACT_INVALID`。它只有以下三项 audit contract mismatch，不是数值失败，也不是资源失败：

1. PETSc/MUMPS factor component memory telemetry unavailable；
2. local/global factor-memory facts 因上述 unavailable 状态未按合法分支闭合；
3. `stage_facts.transfer_counts` 使用真实的 `_total` 键，而 checker-v1 查找了简化键。

checker-v2 没有重跑 setup worker，而是对同一冻结 worker record 和同一 watchdog compact 做离线重判，修正上述 checker 合同后得到：

| R4.2 setup fact | 实测值/状态 |
| --- | --- |
| worker source SHA | `6d5cada617418f9bbdefe4efcb97309a059fac1b` |
| checker 修复 clean HEAD | `9976441a47dc50ea894c3163903c7934d30cfb3d` |
| classification | `SETUP_EVIDENCE_PASS` |
| 当前边界 | `resource-qualified-for-R4.3`；不是 solver/PDE pass |
| cold peak / retained peak | `1,005,158,400 B` / `1,005,158,400 B` |
| process-tree swap | `0 B` |
| 10-apply RSS span | `0 B` |
| linearity / repeat | `7.06986634291602e-16` / `0` |
| independent input relative | `0.9986105202023134` |
| maximum p1 residual | `2.9151260036108388e-16` |
| p1 matrix rows / NNZ / factor NNZ | `1067 / 37253 / 131203` |
| PETSc factor component memory | unavailable；不计入 known bytes |
| known ledger / unattributed remainder | `306,110,231 B` / `699,048,169 B` |

这里的 “factor memory unavailable” 不是说 MUMPS factor 实际占用为零，而是 PETSc 没有提供可用的 component byte telemetry；因此不能用零冒充测量值。完整 process-tree RSS 才是本次资源权威，它包含该 factor 以及无法拆分的其他运行时分配；在 ledger 中，未能拆分的部分保留在 `unattributed`，避免重复计算或虚构 factor 字节。

| Evidence | 路径 | SHA256 |
| --- | --- | --- |
| setup worker record | `outcomes/records/lor_edge_geometric_mg_r4_route_b_setup_v1.json` | `b3e80fa90f472020558e6d4f007a38683098f83e4b7f63d20338d2e1f36477e7` |
| setup watchdog compact（tracked copy） | `outcomes/records/lor_edge_geometric_mg_r4_route_b_setup_v1_watchdog.json` | `32297af93a63548bdd22324352488897bfe601343dc3e9b7fa4d362e20722b25` |
| checker-v1 | `outcomes/records/lor_edge_geometric_mg_r4_route_b_setup_v1_checker.json` | `cadc080c402f0d38ee0adc8952fd93f574fb714394dfc52579f3e8292e9a4fec` |
| checker-v2（同一 worker evidence 的离线重判） | `outcomes/records/lor_edge_geometric_mg_r4_route_b_setup_v1_checker_v2.json` | `7ad5e7112f4ae536baaacdd9341a5b0bdbf3f11447f752c16a1e92fddc452f64` |

当前 `selected_hierarchy=NOT_SELECTED`。R4.3 的 random/gradient/curl/checkerboard 四个 positive case 仍为 pending/not_run；R8 及以后继续为 `not_run_by_gate`，不能把 setup resource qualification 写成最终 solver 或 PDE 通过。

## 不可变历史证据

下面的 compact record 已逐个绑定相对路径和 SHA256；checker 会重新读取文件并重算 SHA，不把旧 record 的 `status` 当作新结论。旧记录、旧阈值和旧失败分类保持原样。

| 历史项 | 保留状态 | 证据入口 |
| --- | --- | --- |
| V10 Q0 Reference E 500-step | `controlled_negative` | `p3_exact_reference_triage_v1.json`、对应 checker |
| foundation-E 3020-step | `pass` | `p3_exact_edge_foundation_10000_v1.json`、v2 checker、watchdog |
| old SLEPc spectral audit | `controlled_negative` | `p3_global_lor_spectral_audit_v1_failure.json`、watchdog |
| HX/PCGAMG closure | `closed` | `lor_native_complex_hx_oracle_v1.json`、additive-v2 campaign |
| V11 S1 global spectral oracle | `pass` | S1 record/checker |
| V11 S2 resource foundation | `pass` | S2 record/checker |
| V11 S4 16-case oracle | `pass_small_oracle_scope` | 两个 tracked S4 compact；其内部保存 source aggregate path/SHA |
| V11 S5 hierarchy capacity | `failed_algebra_gate` | S5 record/checker |
| ba40358 probe-domain attempt | `controlled_negative_probe_domain_invalid` | archived record/checker |

V11 S5 的旧精确阈值和状态特别冻结如下：`energy_gate_limit = 1e-9`，6→3 energy relative 为 `0.04115402900674629`，3→1 为 `2.7851655955739857e-15`，原 checker classification 为 `RESOURCE_OR_ALGEBRA_GATE_FAILED`。本轮没有改写它们，也没有把资源通过改成 solver 通过。

## Provenance 与 checker contract

| 身份 | R0 固定值 |
| --- | --- |
| branch | `codex/20260820-task38-extra-full3d-iterative-0p7nm` |
| source SHA | `9a5015fa04cc92a586baa20a19608af1d0131327`，语义为 R0 未提交 delta 之前的 clean HEAD |
| input | `input/templates/full3d_iterative_example.dat` |
| input/raw SHA | `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41` |
| resolved SHA | `78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad` |
| physical model SHA | `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f` |
| R1 raw artifacts | none created |

独立 checker 使用 strict JSON 解析，显式拒绝 `NaN`、`Infinity` 和 `-Infinity`；缺少字段、路径、SHA、输入身份、branch 或 source 身份时输出 `CONTRACT_INVALID`。R0 checker 从 prospective raw scalar measurement 重新计算 lambda 比值对应的 condition，并检查与 reported condition 的闭合；它不读取 record 的 status 来替代判断，也不声称当前已经从 coarse/fine arrays 重算 q。R1 正式 checker 必须从正式 raw evidence 独立重算 rank/SPD/Hermitian/eigen residual/probe/energy/identity，并且不得导入 runner、solver、PETSc 或 MPI。

S4 的 ignored `aggregate_check.json` 不要求在 clean clone 中存在或现场 hash；两个 tracked S4 compact 已封存其 source aggregate path/SHA。本 compact 只现场 hash 这两个 tracked 文件，并把 aggregate digest 作为 `ignored_raw_digest_preserved_indirectly` 的描述性 provenance。

Route B/C 的字段存在只是为了让未来边界明确，当前均是 `conditional_not_run`，没有实现、没有参数扫描、没有资源或数值结论。

## R0 交付物与检查边界

| 文件 | 作用 |
| --- | --- |
| `src/solvers/fullspace_lor_interlevel_route_selection.py` | 固定门槛和纯数据 route decision helper；不构造数值对象 |
| `benchmarks/task038_full3d_interlevel_route_selection_checker.py` | stdlib + NumPy 独立 contract/measurement checker |
| `src/test/test_314_task038_interlevel_route_selection.py` | 轻量 Gate 边界、六 probe、缺 key、非有限数、冻结 hash、路由顺序测试 |
| `outcomes/records/interlevel_route_selection_v1.json` | `CONTRACT_READY / measured-not-run` compact manifest |

本轮只运行 pure-Python focused tests、相关旧 contract tests、strict JSON、compile/AST/Markdown/diff 检查；不运行 S4/S5、MPI、PDE、R1 spectrum 或任何长 Krylov。任何后续 Route A 正式结果都必须另有 fresh raw artifacts、独立 checker 输出和新的 source SHA，不能回写本 compact。
