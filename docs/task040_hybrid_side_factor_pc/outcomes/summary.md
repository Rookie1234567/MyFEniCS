# Task040 summary — current V9 authority

## V9 current authority（Response v10）

| 范围 | 当前结论 | 证据边界 |
|---|---|---|
| Full-spectrum/source bridge | transform/source measured pass；screen `FULL_SPECTRUM_SWEEP_NO_SIGNAL` | 两源 one-apply 与 r8/r16/r32/r64齐全，strict no-signal |
| C0 | worker one-apply numerical no-signal；watchdog terminal resource metadata gap | `rho_coarse=6.778773552009804`；watchdog gap不推翻 numerical Gate |
| C1 | `not_run_by_numerical_gate` | Review §5.5禁止在 C0 no-signal 后运行同 basis matrix-free |
| V9-E fallback | entry成立但无 qualified physical positive | full-spectrum 与 C0 双真实 no-signal；fallback未产生 qualified physical positive |
| B0/B1/S3/LOR L2/bare-F external | tiny B0/B1 improvement `>=8` Gate 已通过；其余为 exploratory component/formal evidence | B0 serial/MPI2 improvement=`4385921181522.289`/`4178485941698.5303`；B1 serial/MPI2 improvement=`1821946650161.7349`/`2137800826967.3997`；tiny 仅支持 reduced 5 nm pilot 流程进入，不替代 physical formal positive；详值见 [route ledger](route_signal_ledger.md) |
| boundary handoff | 已建立 | 文档记录候选边界；qualified architecture candidate / 0.7 nm capacity 仍未建立 |
| Task040 | `OPEN_AWAITING_REVIEW` | `selective merge=NO`，`master merge approval=NO` |

## 统一 V9 run matrix 与当前实现分组

下表以 raw observed 为主；`measured` 是确实运行并有对应 evidence 的结果，`failed` 是
实现或数值 Gate 未通过，`not_run` 是按 stop rule 没有启动。RSS 用 process-tree peak 的
字节口径，projection 不当作实测峰值；组件结果不当作 V9-E physical positive。

| route/case | 状态 | 最小关键事实 | evidence / baseline |
|---|---|---|---|
| source canonical bridge | measured component pass | MPI8；resource pass；phase-once roundtrip relative `<1e-12` | [source canonical bridge](v9_source_canonical_bridge.md)；source-only component |
| corrected full-spectrum | measured strict no-signal | two sources；r64/drop Gate 未过；wall=`1013.0478316960507s`；RSS=`37884526592 B`；swap=`0` | [full-spectrum](full_spectrum_floquet_sweep.md)；p6h4 raw |
| C0 explicit coarse | measured numerical no-signal；resource metadata gap | one-apply `rho_coarse=6.778773552009804`；raw peak=`86960574464 B`；swap=`0` | [adaptive Stage A/B/C](adaptive_spectral_schwarz.md) + [response C0](../response_v10.md)；C0 raw；无 resource pass 改写 |
| S3 J1 baseline ×3 | failed implementation | shape `8424×300` vs `8424×296`；token `9786` vs `8424`；layers `2` vs `6` | [response V10 ledger](../response_v10.md)；MPI8/threads1；无 numerical Gate |
| LOR L2 h10 / h5 | measured component pass / fail | residual `9.49183402945266e-9` / `3.743078556589845e-7`；211 / 256 steps | [response V10 ledger](../response_v10.md)；max local rows=`432` |
| physical bare-F external h10 | measured worker no-signal；wrapper unresolved | explicit residual=`0.7349227023138162`；corrected root；watchdog resource/result adjudication gap | [response V10 ledger](../response_v10.md)；P+ is right PC only |
| C1, five-source, top/Hybrid, 0.7 nm | not_run | C1 stopped by C0 numerical Gate；其余无 qualified positive入口 | Review V9 §5.5/§9；[boundary handoff](full3d_0p7nm_architecture_handoff.md) |

当前 changed-file/implementation groups 是：source/canonical 与 marker plumbing、full-spectrum
与 C0 route、structured/LOR/external research helpers，以及本组 compact outcomes/response。
它们的依赖、fresh evidence 和合并边界见下方六组表；没有把任何 route 的 raw artifact 当 Git
merge 项。

## Selective-merge dependency groups

| 依赖组 | 文件/依赖 | 数值行为 | 测试/fresh evidence | 建议顺序/边界 |
|---|---|---|---|---|
| production numerical/core | 本轮没有 qualified production core；新增 `src/solvers` research helpers 不属于此组 | ordinary default 未改变 | 无 qualified production fresh evidence | 暂不合入 |
| reusable runner/watchdog | `benchmarks/task040_level_a.py`（混合路线 wiring，仅 file/hunk-level 审阅，排除 S3/未闭合路径）、`benchmarks/task040_level_a_watchdog.py`、`benchmarks/task040_v6_2_interface_schur.py`；依赖 research helpers | 仅 opt-in plumbing；ordinary route 不变 | 对应 raw routes；final closeout contracts 34 passed（本地轻量合同） | 按依赖审阅，仍未自动提升 production |
| checker/benchmark | 本轮未新增独立 checker 或 case record；focused tests 是验证资产，不是 checker | 不改变 solver promotion | test339 stage-time serial/MPI2；其余 raw evidence | 不称为 checker |
| compact evidence/docs | `response_v10.md`、`development_progress.md`、`outcomes/{v9_source_canonical_bridge,matrix_free_galerkin_coarse,full3d_0p7nm_architecture_handoff,full_spectrum_floquet_sweep,adaptive_spectral_schwarz,route_signal_ledger,memory_residual_time_pareto,0p7nm_side_pc_capacity,summary}.md` | 不改变数值 | raw hash、命令和已有 targeted evidence | 作为 compact evidence 归档，不把 raw 当 Git merge 项 |
| research-only | `src/solvers/floquet_background_hcurl*.py`（不含 `floquet_background_hcurl_s3_formal.py`、`floquet_background_hcurl_s3_pilot.py`）、`src/solvers/hcurl_fixed_lor*.py`、canonical/full-spectrum/C0 helpers、`src/solvers/hybrid_bare_f_external_lor_pilot.py`；对应 `src/test/test_298*`、`test_319*`、`test_326*`–`test_329*`、`test_331*`–`test_339*` | 不具 production 资格；ordinary physics/default 不变 | 各 component/focused evidence 与 MPI8 roots | 保留研究/复核，不作 production promotion |
| do-not-merge | `src/solvers/floquet_background_hcurl_s3_formal.py`、`src/solvers/floquet_background_hcurl_s3_pilot.py`、`src/test/test_330_task040_v9_s3b_pilot.py`、`benchmarks/task040_level_a.py` 中的 S3 wiring，以及其他未闭合/旧 raw-row paths | 不提升失败路径为 numerical behavior | failed roots retained/archived；raw artifacts 不是 Git 项 | 明确禁止合入 |

以下既有 V1–V8 内容保留，包含历史状态、失败原因、资源口径和证据入口。

## 当前最终结果

| 阶段/路线 | 当前状态 | 关键 measured / derived evidence |
|---|---|---|
| V7 scale-normalized identity | Review V8 `review_adjudicated=true`；selected=`D0_lower_memory`；`V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0` | raw `formal_adjudication=false` preserved；V6 absolute negative unchanged |
| dedicated full-spectrum | `FULL_SPECTRUM_SWEEP_NO_SIGNAL` | corrected root；两源 one-apply/r8/r16/r32/r64齐全；r64 与 32→64 drop 均未过 strict Gate，不是 implementation failure |
| C0 explicit coarse | worker numerical no-signal；watchdog terminal resource metadata gap | `rho_coarse=6.778773552009804`；worker evidence 与 watchdog raw gap 并列 |
| V9-E fallback | entry established；无 qualified physical positive | corrected external bare-F worker residual=`0.7349227023138162`；watchdog raw `requires_result_adjudication` |
| LOR L2 h10 / h5 | component action-screen pass / h5 refinement/action-screen negative | h10=`9.49183402945266e-9`，211；h5=`3.743078556589845e-7`，256、reason `-3`；不外推为 h-independent conclusion |
| adaptive Stage A | `V8_ADAPTIVE_STAGE_A_LOCAL_GATE_PASS` | 630 patches；rows=`432/432/432`；POU=`0`；setup=`255.8505309909815s`；one-apply=`3.498585887020454s`；global true residual rel=`2.390497409724407` 不作 Gate failure |
| exact generalized B1 | `not_completed_at_10800s` | root=`results/task040_v8_adaptive_stage_b1_mpi8_0e92079f_fix1`；wall timeout=`10800s`；无 run summary/数值结果；允许转 economical，不是 numerical no-signal |
| adaptive Stage B/C | `ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE` | natural rc0；peak=`19786649600 B`=`18.427753448486328 GiB`；projected=`130502065136 B`=`121.539519295 GiB`；hard=`45 GiB`；P/PH/FP/Ac/KSP=`0` |

## 资源与生命周期摘要

| 项目 | 当前值 |
|---|---:|
| Stage B/C live baseline | `19658432512 B` |
| Stage B/C projected peak / headroom | `130502065136 B` / `-82183683056 B` |
| BC harmonic columns | 630 patches × 160 modes；total coarse DoF=`100800`；570 classes；reuse saved=`60`；multi-RHS=`630` |
| BC projected object components | P `871970408`；P_H `871718408`；F*P `10653602408`；P_HFP `24945446408`；PETSc overhead `37342737632`；iterative `543312000`；MatProduct `35599048816`；workspace `15796544` B |
| BC final cleanup | complete；bare-F before/after=`1cc07ab68ed747abfe7599ce1fdfeff95642653b29863d6f261e2fe9239d574f` |

`130502065136 B` 是 conservative symbolic projection；实测 peak 只有 `19786649600 B`，两者不能混称。`factor_bytes_global=0` 仅为 diagnostic release 后字段，不表示 factor-free 完成。

## 当前裁决与未运行项

Task040=`OPEN_AWAITING_REVIEW`，`selective merge=NO`。V9-E 入口已成立，但 fallback 没有 qualified
physical positive；boundary handoff 文档已经建立，而 qualified Full3D architecture candidate 与
0.7 nm capacity 仍为 `NOT_ESTABLISHED / resource-blocked`，不能解释为物理不可行。master、Task39、
physics、M480、physical DtN 和 ordinary defaults 未改。Full repository pytest、
MPI4、CI、C1、Stage C numerical checkpoints 与 0.7 nm/2 TB PDE 均未运行。

旧的 V7/V8 预运行快照如下保留，仅用于历史追踪，不覆盖当前 authority；其中“未运行”或“未建
handoff”均明确指 V8 当时，不描述 V9 current。

## 历史 V8 authority（继承 V7 identity）

## V8-0 adjudication / V8-1 route

| 项目 | 当前裁决 |
|---|---|
| V7 identity | `V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0`；`review_adjudicated=true`；`selected=D0_lower_memory` |
| raw formal field | `raw_formal_adjudication=false_preserved`；V6 absolute negative unchanged |
| V8 当时 V8-1 dedicated route | `--v8-full-spectrum-only`；已启动但在 source/integration failure 前未形成 numerical screen；raw root=`089bf8a1` |
| review binding | V8 review=`0ce67c0c68c36e9677f3293a87c1c124e82c6f70`；input/physical/resolved/selected/bare-F 与 V7 bundle 见 [V8 adjudication](v8_review_adjudication.md) |
| prior implementation evidence | full-spectrum fix=`a2acb9344a9bd246a399c9110207926c7e03460e`；moving-PML owner-serial implementation retired，method family not numerically rejected |

V8-1 专用路线必须复用已裁决的 D0、current bare `F` 与 V5 authority，但不调用旧三尺度
identity、D0/D1 comparison、refinement/partition、exact packet 或 moving-PML。未形成 numerical
结果前，不把它写成 positive 或 no-signal。

Task040 研究的是：在不改变裸算子 `F` 和物理方程的前提下，能否用较小的侧向/局部逆作用
代替完整 side factor。V7 的 moving-PML 先在人工边界加 PC-only 吸收层，目的是测试波能否
在较低内存路径上传递；它改变的是预条件器（帮助外层求解），不是物理方程本身。

当前唯一正式 moving 结论为：

| 路线 | 状态 | 关键事实 |
|---|---|---|
| V7 scale identity | candidate pass，非 formal adjudication | 3 scales、D0/D1、三层 raw/checker 通过；full-spectrum 随后实现错误 |
| full-spectrum Floquet/FFT | 未资格化 | canonical metadata/probe 两次具体实现失败；无 numerical no-signal |
| moving-PML corrected MPI8 | `INCONCLUSIVE_RESOURCE_GATE / SIGNAL_UNAVAILABLE` | `21601.760233s` wall；RSS `40560816128 B`；swap `0`；未到第一个 source checkpoint |
| adaptive Schwarz | `NOT_RUN_DUE_TO_TRUE_RESOURCE_GATE` | V7 §10.3 真实 wall/resource stop；adaptive 未启动且不是 adaptive negative |

因此 Task040 **open / review required**，`merge approval=NO`。没有把资源停止写成算法 no-signal，
也没有宣称 0.7 nm 无解。V8 当时的 0.7 nm capacity derivation、Full3D architecture handoff、
factor-free local service、h3 和完整 Hybrid 均未到达/未资格化；这不覆盖当前已经建立的
boundary handoff 文档。

V6-2 absolute-threshold negative 仍保留：classification
`V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL`；Gamma/interior/linearity/repeat 观测分别为
`3.783538480529195e-10 / 1.2298155651030158e-9 / 6.766170711131541e-9 /
1.4161645932820494e-9`，对应旧阈值 `1e-10 / 1e-10 / 1e-11 / 1e-11`；zero 与 roundtrip
为 `0`。这不是 exact numerical negative。

master、Task39、physics、M480、physical DtN 和 ordinary defaults 未改；本轮 result roots
均为 ignored artifact，仅在 [V8 response](../response_v8.md) 与相关 outcome 中按精确路径和
hash 引用。

# Task040 结果摘要

Task040 研究的是：在冻结 Hybrid 方程、裸算子 `F`、物理输入和 M480 不变时，能否用较小的
side inverse（侧向逆作用）替代完整的 exact side factor。通俗地说，side inverse 试图只
在人工截面附近保留必要的信息，以减少内存；但它必须先证明传递方向正确，再谈完整 Hybrid。
本页把已完成的 T40-3、V1-1 与 V1-2 Run B 分开登记，不能把组件峰值当作完整工作流节省。

截至 Response V7 / V6-2 收口时的 authority：`valid_identity_negative`；formal 与独立 checker
classification 均为 `V6_2_FULL_INTERFACE_SCHUR_IDENTITY_FAIL`，状态为
`completed_v6_2_identity_gate_negative`。
checker `checker_pass=true`、`evidence_valid=true`、`gate_pass=false`、`executed_exact=false`。
Review V6 §19.1 的“full-interface Schur action identity 无法建立”stop Gate 已触发；后续
full-spectrum、moving-PML、adaptive Schwarz、factor-free local service、bottom/top/both/full
Hybrid、h3、0.7 nm 与 Full3D 均为 `not_run_by_v6_2_identity_gate`（以上为当时快照，已由本页
顶部 V7 后续执行记录 supersede）。这是 valid identity
negative，不是 exact numerical negative。V5 Route C 的历史 authority 仍保留在下文。

## Review V4 历史收口

| 项目 | 当前结论 | 证据边界 |
|---|---|---|
| V4-1 exact-authority preflight | `controlled_identity_negative`；`EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F` | 唯一 identity failure 为 `canonical_source_binding` / `CANONICAL_SOURCE_ROW_BINDING_UNAVAILABLE` |
| 身份证据 | 5 labels、80 个目标 JSON、96 个 spool JSON；11 项 identity checks 中 10 项通过 | metadata self-hash、array/local hash metadata、producer 8/8、exact identities、input/physical/selected/probe/spool/resolved/source/branch 均通过；canonical descriptor/source-row binding 没有 |
| 原始检查器 | `checker_pass=true`、`evidence_valid=true`、`gate_pass=false` | 37/37 checks；105 read files；无 NPY 数值读取；checker artifact SHA `71ab1274b3b236679ff19b403875b0109f6f3e3c1bb1f02e2642ee69d44f97d8` |
| 构造与数值 | system/F/interface mass/Vec/factor/QEP/PDE 均未构造或未运行 | bare-F、A_side、trace/dual/projection/lift、response/FGMRES/coarse/Level B/full Hybrid/h3 均无数值 |
| 资源 | watchdog MPI8、threads1、rc0 natural、20/20 samples、最后 sample `9.697888669999884 s`、peak `1764352000 B = 1.643180847167969 GiB`、swap0 | runner 内部 resource authority 为 sample0、`not_run_by_identity_gate`；metadata preflight 不是 Pareto solver 点 |
| V4-2→V4-10 | `not_run_by_v4_1_identity_gate` | 没有新的 R/T/A、DoF、field、rank、scaling 或 production 资格数据 |

“canonical source-row bridge”可以直译成“把旧文件中的行号对应回当前物理自由度的地图”。
冻结 spool 的文件和 hash 虽然正确，但没有这张地图；旧 MPI8 ownership 与当前布局不同，因而
不能把 raw PETSc global row 直接搬运成当前 `F` 的数学行。这个结论不是数值 residual 失败，
不是 exact vectors 错误的证明，也不是 trace/lift/PC 失败；它只说明当前冻结 exact output
不能安全重建到 current bare `F`。完整受控记录见
[V4-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v4_1_exact_authority_compatibility_v1.json)。

正式 V4 root 是唯一的 `9f3d6e39` root。旧 root `a64d33e6` 是跨 ownership 的 raw-row remap
`implementation_failure`，`1c68da98` 是 `incomplete_superseded`；两者保留但不混入当前 formal
数值或资源结论。

## Review V5 当前收口

| 项目 | 当前结论 | 证据边界 |
|---|---|---|
| V5-1 operator semantics | static source audit 已完成并 hash-bound；current modal source 保持 `full3d_one_cell_exact_schur` 定义 | 只完成语义/路径审计；runtime qualification 仍需数值 Gate |
| V5-2 fresh bare-F authority | `FRESH_BARE_F_AUTHORITY_RESOURCE_BLOCKED` | 部分完成后授权 `21600 s` factor-construction 窗口耗尽；one-cell source factor `1→0`，五个 RHS/owner-sharded canonical/Gamma layout 已写出；full-side 只到 `v5_bare_f_factor_setup_begin`，无 factor-ready、无 exact packet |
| Route C online screen | `ROUTE_C_NO_SIGNAL`；最终 checker classification `VALID_NEGATIVE_ROUTE_C_NO_SIGNAL_RESOURCE_AUTHORITY_GAP` | 两源到 128 步；no-signal 独立重算通过；resource authority 因中段 live-unreadable rows 不完整 |
| Route C raw resource | raw RSS below hard、raw swap zero；authority completeness false | peak `30254075904 B` < `48318382080 B`（45 GiB）；第 5825/5826 行 live unreadable，末尾 21296/21297 才是可排除 cleanup suffix |
| 后续 V5 漏斗 | 全部未运行 | `not_run_by_route_c_no_signal_and_resource_authority_gate`；不继续 rank、Level B、top、full Hybrid 或 h3 |

Route C 的两个 RHS 是 `external_dtn_coupling` 与 `fixed_random_repeat_0`。它们的
`(r64,r128,log10(r64/r128))` 分别为
`(0.8906247440000827, 0.9116861468870889, -0.010150598869495011)` 和
`(1.036891675911675, 1.0585987178847864, -0.008997975654488713)`；两者均满足
`r128>0.9` 且下降小于 `0.05 decade`，共享稳定方向数为 `0`。因此这是停止 Gate，不是
允许继续的 candidate pass。正式 raw root、derived checker 和独立信号账本分别见
`results/task040_v5_route_c_online_long_fgmres_mpi8_b5b765ef_retry1`、
`results/task040_v5_route_c_teardown_adjudication_b5b765ef/checker.json` 和
[Route C signal ledger](route_signal_ledger.md)。

V5 Route C 的实现范围是新鲜进程中的 bottom-only online screen：`system_created=true`、
`rhs_vectors_loaded=2`、`exact_output_vectors_loaded=0`、`qep_calls=0`，三个诊断 group
factor `3→0`，full-side exact factor `0`；external minimal RHS 的两次构造仍为 C/D/H `0`、
component instances `4`、peak live components `2`。这些是本次 screen 的 inventory，不是
production side inverse 或 full Hybrid 资格。

V5-2 producer 的资源事实为：preferred `59055800320 B`（55 GiB）、warning
`62277025792 B`（58 GiB）、hard `68719476736 B`（64 GiB），实测 peak
`45432283136 B`、swap authority `0`。进程在 `21600 s` wall window 内未到 full-side
factor-ready；因此 full-side bare-F factor 要求的 `1→0` 没有完成，OS teardown 不能被记作
PETSc lifecycle pass。该 producer 不是 64 GiB hard stop、不是 numerical fail；Route C 的
正式 screen 在另一个 fresh process 完成。

### 实现范围 / 下一步 / selective merge 边界

本轮实际触及的实现文件包括：`src/solvers/hybrid_exact_authority_compat.py`、
`src/solvers/hybrid_bare_f_authority.py`、`src/solvers/hybrid_route_c.py`、
`src/coupling/hybrid_one_cell_exact_traction_builder.py`、
`benchmarks/task040_level_a.py`、`benchmarks/task040_level_a_watchdog.py`，以及对应的
V4/V5 checker 与 focused tests。它们的 V5 route 是互斥 opt-in 的诊断路径；ordinary
production solver/default 未改变，fresh evidence 也没有把这条路径提升为 production side
inverse。

若未来重新打开该问题，第一步必须先取得新的 Review 授权并重新定义 fresh current-layout
authority 与资源证据；不得复用旧 raw-row remap，也仍禁止重建 full-side exact factor。当前
`ROUTE_C_NO_SIGNAL` 与 resource-authority gap 之前，V5-2→V5-10 不得运行；merge approval
仍为 **NO**。

V5-1/V5-2 与 Route C 的 implementation、测试和边界见
[operator semantics audit](authority_operator_semantics.md)、
[fresh authority outcome](fresh_bare_f_authority.md) 和
[V5 test summary](test_summary.md)。旧 V4 compact record 保持原字节不变；V5 checker 的
evidence 是独立派生结果，不改写原 watchdog summary。下方较早的 V4 段落是历史记录；其中
“未来先建立旧 bridge”的导航已由本节的 V5 fresh current-layout authority/Route C 结果取代，
不能作为当前下一步指令。

## Review V4 实现范围、下一步与 selective merge 边界

V4 整轮的实现范围包括：`src/solvers/hybrid_exact_authority_compat.py` 诊断兼容性 helper；
`benchmarks/task040_level_a.py` 的互斥 opt-in metadata preflight/identity-stop route；
`benchmarks/task040_level_a_watchdog.py` 的 route/marker 透传；对应的 test313 serial/MPI2/MPI4
回归；独立 checker `benchmarks/check_task040_v4_exact_authority.py` 及 test314。现有 ordinary
production solver 路径和默认行为没有改变，但这些 helper/opt-in route 也不构成 production
side inverse 资格。

| 依赖组 | 文件归属与边界 |
|---|---|
| production numerical/core | 现有 production 数值路径/default 未改变；V4 helper 不作为 production qualification |
| reusable runner/watchdog | `benchmarks/task040_level_a.py`、`benchmarks/task040_level_a_watchdog.py`、`src/test/test_313_task040_v4_exact_authority.py`；只新增 opt-in route，依赖 helper，不改变其他 route 默认行为 |
| checker/benchmark | `benchmarks/check_task040_v4_exact_authority.py`、`src/test/test_314_task040_v4_exact_authority_checker.py`；独立 raw 重算，不读 numeric NPY |
| compact evidence/docs | compact record、16 个 outcomes 文档、`response_v5.md` |
| research-only / do-not-merge | diagnostic helper、ignored formal/invalid roots，以及 raw-row remap 和无效 residual/未完成路径；不得当作 production side inverse |

若未来继续，第一步必须经新的 Review 授权，取得与 source SHA 绑定、可逆、覆盖完整、满足
Floquet consistency 且通过 round-trip 的旧 source-row 到 canonical physical key bridge；仍
禁止重建 full-side exact factor。在该 bridge 资格化之前，V4-2→V4-10 不得运行。merge
approval 仍为 **NO**。

## 阶段总表

| 阶段 | 作用范围 | 状态 | 关键事实 |
|---|---|---|---|
| T40-0 | inherited audit | completed | 冻结身份、ABI、基线与禁止路线已绑定 |
| T40-1/T40-2 | F/action identity、人工界面阻抗与 MPI tiny identity | completed | `q=-i beta`、两界面 mass/support、bare `F` unchanged |
| T40-3 | bottom bare-F one-apply transmission oracle | controlled numerical negative | `TRANSMISSION_MECHANISM_FAIL`；worst rho `28.316064601533686` |
| V1-1 | fixed scalar transmission right-FGMRES screen | controlled numerical negative | `SCALAR_TRANSMISSION_DIRECTIONAL_FAIL`；五个 `r16 >= 0.9`，32 not run |
| V1-2 | exact interface Schur/Steklov sampled audit | controlled resource stop | `45.05752944946289 GiB` hard stop；仅到 exact oracle ready/release，未完成数值资格 |
| V1-3 | conditional projected-exact transmission | setup_started_but_not_ready | setup 已开始但未到 `projected_ready`；resource stop，numerical capacity `NOT_EVALUATED` |
| V1-4 | analytic mode-aware transmission | not_run_by_gate | V1-3 setup 未到 ready，前置 Gate 未完成 |
| V1-5 | conditional bounded-patch Level B | not_run_by_gate | V1-2/V1-3 前置 Gate 未完成 |
| V1-6 | bottom/top/both/full Hybrid | not_run_by_gate | V1-5 未运行 |
| V1-7 | conditional h3 scalability probe | not_run_by_gate | V1-6 未运行 |
| V1-8 | evidence/docs closeout | completed | 本页、compact record 与 `response_v2.md` 已完成并通过轻量合同检查 |
| V2-A1 | interface-Schur packet producer | completed_diagnostic_oracle | packet 完整、独立 checker 通过；这是诊断/oracle authority，不是 scalable side inverse 或 V2-B 结果 |
| V2-B2 | fresh projected-transmission consumer | controlled numerical negative | resource/identity/remap 通过；五个 `r16 >= 0.9`，32 未授权；`THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT` |
| V2-C–V2-F | analytic / Level B / full-side / h3 | not_run_by_gate | V2-B2 数值 Gate 失败后按决策树停止 |
| V2-G | evidence/docs closeout | prepared_pending_review | compact record、consumer outcome、response_v3 与本页同步完成，待审阅 |

## 正式身份与最新 Run B 资源

| 字段 | 值 |
|---|---|
| source SHA | `16ecba568be901325e53c3652aa10bb432de5a6b` |
| MPI / threads | `8 / 1` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected packet manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| V1-2 probe manifest SHA256 | `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` |
| exact-spool catalog SHA256 | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| formal root | `results/task040_v1_2_v1_3_run_b_mpi8_16ecba56` |
| watchdog termination | `absolute_memory_limit`; process group SIGTERM；未需 SIGKILL |
| hard stop / peak RSS | `48,318,382,080 B` / `48,380,153,856 B` |
| peak RSS | `45.05752944946289 GiB`；约高于 hard stop `61,771,776 B` |
| peak swap / status readability | `0 B / all_status_readable=true` |
| wall口径 | process-sample `1485.4694942460628 s` |

最新 root 到达 `system_ready`、两个 interface mass ready、`projection_begin`、
`v1_2_exact_oracle_ready` 和 `v1_2_exact_oracle_released`。exact oracle 的 factor count
是 `3 -> 0`，lower/upper mode count 为 `296/480`。随后代码已进入 V1-3 projected
transmission 的 setup，RSS 继续增长，但没有发出 `v1_3_projected_ready` marker，也没有
`run_summary.json`、per-probe contractions、rank/condition 或 one-apply/FGMRES checkpoint。
因此 V1-2 仍是 `not_qualified_due_resource_stop`，V1-3 是
`setup_started_but_not_ready`、同样因资源停止未资格化；V1-3 numerical capacity 为
`NOT_EVALUATED`，不能分类为 `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT`。

## 已完成数值结果与资源边界

| 路线 | 结果 | process-tree peak | wall | 状态 |
|---|---|---:|---:|---|
| T40-3 bottom bare-F component | 五个非零 rho 全部大于 1；worst `28.316064601533686` | `28.333576202392578 GiB` | `660.6481867840048 s` | `TRANSMISSION_MECHANISM_FAIL` |
| V1-1 scalar component | 五个 `r16 >= 0.9`；32 not run | `27.790115356445312 GiB` | `669.4473022361053 s` | `SCALAR_TRANSMISSION_DIRECTIONAL_FAIL` |
| V1-2 Run B | exact oracle ready/released；数值 probe 未序列化 | `45.05752944946289 GiB` | `1485.4694942460628 s` | `V1_2_RESOURCE_HARD_STOP_BEFORE_NUMERICAL_QUALIFICATION` |
| inherited direct full workflow | matched reference | `93.377006531 GiB` | inherited | reference |
| inherited exact-side iterative full workflow | residual/physics/lifecycle pass | `80.025856018 GiB` | inherited | reference |

28.333576202392578 GiB、27.790115356445312 GiB 和 45.05752944946289 GiB 都是各自
组件或失败尝试的 process-tree 峰值，不是完整 workflow saving tier。PSS/USS 在最新 raw
中没有记录，不能从 RSS 推算。最新 hard stop 也不能说明 projected transmission 的数学
机制失败：它只说明同一进程的资源生命周期在完成 exact oracle 后仍未能在安全线内完成后续阶段。

## 生命周期与停止解释

`v1_2_exact_oracle_ready` 证明三个 exact oracle factor 已构造；紧接的
`v1_2_exact_oracle_released` 证明其 recorded factor count 已回到 0。它不等于 projected
transmission 已经作用或通过。PETSc、MPI、allocator 和后续 trace/projection 对象可能仍保留
进程 RSS；对象逻辑销毁与操作系统立即回收页不是同一件事，所以 factor count 变为 0 后，
后续构造仍可能继续推高 RSS。

## 依赖阶段

V1-4 至 V1-7、Level B、top、full Hybrid 和 h3/0.7 nm scaling 全部
`not_run_by_gate`；V1-3 仅有未完成的 setup，numerical capacity 未评估。当前证据不能判断 bounded local patch 是否失败、是否必须引入 coarse
information，也不能判断完整 Hybrid 或 0.7 nm feasibility。若未来继续，首先应审查阶段分进程、
持久化 V1-2 packet 或有证据的 collective heap trim；本轮未实现这些方案。

## 选择性复用边界

| 类别 | 内容 | 结论 |
|---|---|---|
| reusable candidate | package-invocation watchdog regression、interface support/mass audit、factor owner cleanup | 可独立审阅；未改变 ordinary defaults |
| research-only | 三个 cross-section exact oracle、固定一阶 impedance、V1-2 resource-stop evidence | 保留证据；不是 scalable side inverse |
| do-not-promote | V1-2 未资格化的 projected route、T40-3 action、full Hybrid、0.7 nm capacity claim | 禁止提升 |

完整 raw 和日志留在 ignored `results/`；轻量证据见
[V1-2 resource-stop compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v1_2_v1_3_run_b_resource_stop_v1.json)。

## V2-A1 producer 结果

V2-A1 使用独立 producer 进程在同一冻结 5nm/1deg/phi0/S/p6h4/M480/MPI8 配置下完成
hash-bound interface-Schur packet。它的作用是把人工截面的精确信息整理成后续 consumer
可以读取的诊断包；它没有运行 PDE、QEP、FGMRES，也没有构造 V1-3 projected factor。

| 项目 | 实际结果 |
|---|---|
| producer source / checker-fix SHA | `942c43881e4162085348c48b09c79fbbdac18cd9` / `bd70ab98009de2a2b45561793be6418a6a9bfcc8` |
| formal root | `results/task040_v2_interface_packet_producer_mpi8_942c4388` |
| exit / wall | natural exit, rc0 / `1202.5501016210765 s` |
| peak / preferred / hard | `30,823,858,176 B = 28.706954956054688 GiB` / `<=45 GiB` pass / `55 GiB` 未触发 |
| swap / A2 fallback | `0 B` / `not_run_not_needed` |
| packet | 34 files, 653,804,117 B；24 owner-row shards |
| Gamma rows / modal spans | `7560/15120/7560` / `296/776/480` |
| Gram rank / condition | `296/776/480` / `187.9352369709664`, `1075856.58741676`, `113913.61949721041` |
| reports | physical/interface/middle/complement `15/8/8/4` |
| lifecycle | exact oracle `3 -> 0`；full/global/nested `0/0/0` |

首次 checker 失败是 schema implementation failure：真实 physical report 没有 `finite` marker，
但其显式数值字段和 contractions 全部 finite；旧 checker 错误要求该 marker。修复后
serial/MPI2/MPI4 的 test306 均为 `6/6 passed`，fresh checker `rc0`。producer packet、
历史失败输出和 V1 resource stop 均保留，未被改写为算法负结果。

本次 packet 只证明 diagnostic/oracle authority 和可复核的 owner-row 数据包完成；
`max_projected_exact_relative=1.0281892054707484` 不是 V2-B Gate。V2-B2 consumer 已完成
一次正式 fresh screen，但数值 Gate 为负，当前没有新的 full-workflow saving tier；完整 workflow baseline 仍以
`93.377006531 GiB` direct 和 `80.025856018 GiB` exact-side iterative 为准。详细身份、
raw hashes 和 checker 输出见
[V2-A1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v2_interface_schur_packet_producer_v1.json)
与
[V2-A1 producer outcome](interface_schur_packet_producer.md)。

## V2-B2 fresh projected-transmission consumer

consumer 从 V2-A1 packet 读取并按 canonical key 重新分发 owner-row；它没有重建 exact
interface oracle、QEP 或 PDE。formal process-sample wall 为
`1077.3351624270435 s`（raw timeline 最后一行），producer 的
`1202.5501016210765 s` 是另一个进程的 component wall，二者不能相加成 cold/reuse 或
完整 workflow 时间。

| 项目 | 实际结果 |
|---|---|
| source / checker fix | `40b25d3281d9ce1707f6069607bfdbbf6a3ab48d` / `0919ed2fa3bd1541f543057721fff84fa110f3d4` |
| formal root | `results/task040_v2_projected_packet_consumer_mpi8_40b25d32` |
| exit / peak / swap | natural exit, rc0 / `34,846,629,888 B = 32.453453064 GiB` / `0 B` |
| process-sample wall | `1077.3351624270435 s` |
| remap | `7560/15120/7560` global rows；local target `912/1842/930`；roundtrip `0` |
| one-apply | implementation subset pass；6/6/1 applies，delta `13` |
| FGMRES | phase1 `0/4/8/16` finite；五个 `r16 >= 0.9`；conditional32 `false`；first preferred `null` |
| lifecycle | same three group factors viewed as ready/projected `3`；cleanup `0/0`；simultaneous max `3` |
| classification | `THREE_GROUP_MODE_SUBSPACE_OR_SWEEP_INSUFFICIENT` |

原始 watchdog 因最后一个 cleanup-complete teardown sample 的退出竞态报告 unreadable；原始
文件没有改写。独立 legacy lifecycle audit 绑定 timeline hash，验证 `2137=2136+1`、前
`2136` 行可读且 swap 为零，得到 derived resource pass。这个修正只解决 telemetry lifecycle
语义，不能改变五源残差的数值负结果。组件峰值也不能称为完整 workflow saving tier。

## V3 启动状态

V3 只研究把三个独立 projected inverse 加 sweep 改为 lower/upper 联合接口 reduced solve；
物理、bare `F`、M480、DtN、global Hybrid 和 ordinary defaults 均冻结。V3-0 已完成继承审计；
V3-1 augmented evidence 已完成；未预写，表内只记录实测结论。

| 阶段 | 范围 | 状态 | 当前事实 |
|---|---|---|---|
| V3-0 | inherited audit | `docs_completed_pending_review` | 已绑定 V2 packet、身份、基线与禁止项；无数值运行 |
| V3-1 | packet-only coupled algebra | `completed_with_augmented_packet_pass` | legacy V2 packet 首次审计仍为 `COUPLED_PACKET_INFORMATION_INCOMPLETE`；augmented middle Schur packet 独立 checker 通过，joint rank/condition 与四 block 已绑定 |
| V3-2 | full-span 776 mechanism | `completed_numerical_negative` | `COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL`；identity/resource/lifecycle通过，五源 full bare-F residual不足 |
| V3-3 | bounded rank 64/128/256/512 | `not_run_by_v3_2_numerical_gate` | V3-2 数值 Gate 未通过，未选择 rank |
| V3-4 | packet-independent production | `not_run_by_v3_2_numerical_gate` | V3-3 未运行，未建立 packet-independent candidate |
| V3-5–V3-7 | Level B、bottom/top/full、h3 | `not_run_by_v3_2_numerical_gate` | V3-2 数值 Gate 后停止 |
| V3-8 | evidence / response_v4 | `completed` | compact record、consumer outcome、summary、Pareto、test summary 与 response_v4 已绑定 |

## V3-2 full-span formal consumer

V3-2 的 full776 联合接口 consumer 在固定 `5 nm / 1° / phi=0 / S / p6h4 / M480 / MPI8`
身份下自然退出 `rc=0`。它把三个独立 projected inverse 加 sweep 替换为显式
`LL/LU/UL/UU` 联合 reduced solve，并保留三个 group factor；没有构造 exact-interface
oracle、full-side/global factor，QEP 为 `0`、PDE 为 `not_run`。

| 证据 | 实测值 |
|---|---|
| source / checker | `c11aea058d01e86052d5490a71575a375e3fe207` / `0fbc33d07d27f8e4b2bce9c2bae2704ea9372c7b` |
| joint | `776×776`，rank `776`，condition `72530856.63880321` |
| remap | global rows `7560/15120/7560`，group1 local `1902→1884`，roundtrip `0` |
| one-apply | action count `15`；zero/repeat/linearity/coarse/factor identity 全真 |
| FGMRES | 五源 r16=`0.9706859881–0.9832307912`；32/64 未授权；first preferred `null` |
| resources | `28,044,996,608 B = 26.118938446045 GiB`，swap `0`，wall `892.680907273083 s` |
| lifecycle | group factors `3→0`，reduced factor `1→0`，exact/full/global/nested `0/0/0/0` |
| final classification | `COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL`，`evidence_valid=true` |

这证明 full-span 联合机制的身份、资源和实现证据成立，但当前 296/480 mode span 与
harmonic lift 对完整 bare-F 的残差改善不足；它不能被表述为 production、完整 workflow 或
0.7 nm 资格。V3-3 至 V3-7 均为 `not_run_by_v3_2_numerical_gate`，V3-8 仅完成证据收口。

完整字段和 artifact hash 见
[V3-2 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v3_2_full_span_consumer_v1.json)
与 [V3-2 outcome](coupled_interface_consumer.md)。
