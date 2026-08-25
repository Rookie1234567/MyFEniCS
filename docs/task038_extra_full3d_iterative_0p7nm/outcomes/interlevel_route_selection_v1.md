# Review V12 R0：interlevel route selection v1

## 当前结论

R0 只冻结下一阶段的审计合同，并检查证据身份；它没有运行新的矩阵、谱计算、MPI、PDE 或 S5 重跑。因此当前结论是：`CONTRACT_READY / measured-not-run`。这表示“规则已经写清楚并可由独立 checker 重算”，不表示 Route A、B 或 C 已通过。

| 项目 | R0 状态 | 边界 |
| --- | --- | --- |
| Route A：p6→p3 的固定谱审计 | `not_run` | 只能在 R1 获准后测量 |
| Route B | `conditional_not_run` | 只有 Route A Gate 失败后才可进入 |
| Route C | `conditional_not_run` | 只有 Route A、B 都失败后才可进入 |
| R2 正定 GMRES | `not_run` | 只有 Route A 全部 Gate 通过后才可进入 |
| heavy/MPI/PDE | `not_run` | 本轮明确禁止 |

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
