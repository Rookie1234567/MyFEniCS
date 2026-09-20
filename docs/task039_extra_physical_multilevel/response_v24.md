# Task39extra Response V24：V23 original-B fresh 与登记 bug replay 结果

本轮完成同一 `990-cell original B` 的一次 V23 fresh 运行，以及一次登记的 implementation-bug replay；计算结束后仅整理证据，未追加 PDE。首场 H6 几何实现 bug 已在 replay 前按既有范围修复并通过 16 项几何测试；没有启动 C、没有重新运行 notch、没有更换 PC。以下结论不是总体数值 PASS：B 的完整求解完成，但独立 checker 因一次原有在线 p4 A4 质量 Gate 超限而为 `FAIL`。

## 第一屏结论

| 模型 | 当前状态 | 步数/时间 | RSS 与证据边界 |
|---|---|---:|---|
| O10 historical original baseline | `PASS`，只读对照 | 112 步；`1479.1772295139963 s` monotonic | RSS `2831749120 B`；不是本轮 fresh PDE |
| A `Z2_NOTCH_H10` | `MATCHED_REFERENCE_PASS`，历史已完成 | 146 步；`1648.8478095369937 s` monotonic；independent A6 `9.756517234802322e-7` | RSS/PSS `2297982976/2267706368 B`；旧证据，不重跑 |
| B `Z3_ORIGINAL_H7P5` V23 replay | **求解完成，但总体不全 PASS**；checker `58/59`，唯一失败为在线 p4 A4 数值 Gate | 126 步；KSP `4737.310983555995 s`；全流程 monotonic `5581.178597819002 s` | RSS `7387607040 B`；完整场/物理输出已保存；无同离散参考，`AUTHORITY_LIMITED` |
| C `Z4_NOTCH_H7P5` | `NOT_RUN_BY_SCOPE` | — | 不因 B 完成而自动启动 |

本次 B replay 的三层状态保持分开：

| 层 | replay 状态 | 含义 |
|---|---|---|
| worker summary | `Z3_ORIGINAL_H7P5_AUTHORITY_LIMITED_PASS` / `DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED` | A6、场、物理输出与资源清场适用项完成；不是 matched-reference 资格 |
| parent/watchdog | `worker_exit0` / `COMPLETED`，descendants cleared | replay 正常退出；首场 implementation-bug 的 `WORKER_FAILED` 仍保留在同一 ledger |
| independent checker | `V23_FULL_PHYSICAL_CHECK_FAIL`，`evidence_valid=false`，`official_result=false` | 59 项中 58 项通过；唯一失败是原 `online_native_A4`，不得改写成总体 PASS |

## 身份、数值和物理证据

正式运行源码为 `d3596ac31bdabc2bb9233963adea3e91ddc2f220`，基线为 `8700e65c68b57455586df41f37484d37397dda92`，分支为 `task39extra`；本次 checker 代码也绑定该已测 source，未另改 checker，保存的 raw checker result SHA 为 `a875ba4e494b517e542c7f49690d814de610f7fc369887072dbff84697076f71`。文档 JSON 的 `metadata_commit_sha` 为 `null`，并标注 `identified_by_containing_git_commit`，由包含它们的提交回执识别，不能与 formal source SHA 混用。旧 109 份历史文件、27 个旧 profile、旧 V21/V22 ledger 均保持原 hash。

求解与生命周期事实：

| 项目 | measured / derived 事实 |
|---|---:|
| outer FGMRES iterations | `126` |
| independent final A6，释放前/后 | `9.2831649554582e-7` / `9.2831649554582e-7` |
| KSP lifecycle | create/solve/destroy 各 `1`；zero initial guess；FGMRES restart `32`、max `2048` |
| BAL/H6/p4 调用 | `127` BAL_H、`127` H6、`254` p4 native A4 calls |
| native original-A6 RHS norm | `1.4293543003082507`（字段 `native_rhs_norm`）；`rhs_is_mpc_dual=true` |
| internal RHS norm | 本场未单独记录；不由 native original-A6 RHS norm 推断 |
| internal residual | `9.740172739041228e-18` |
| port closure | `6.625683353415977e-16` |
| complete field/curl | electric、magnetic、auxiliary、power、curl 均 finite；curl postprocess `true` |
| field export peak values | `max_abs_E=0.8303744002152752`，`max_abs_H=0.0022039468031068983` |

官方 port 口径的物理量为：

| 指标 | measured 值 |
|---|---:|
| `R` | `0.3650975537006217` |
| `T` | `0.013016803347759965` |
| `A` | `0.6218856429516183` |
| `A_volume` | `0.6218856421339087` |
| `R00_s` | `0.3650608628870448` |
| `R00_p` | `3.427344920479581e-25` |
| `R00_total` | `0.3650608628870448` |
| port channels | `80/80` checked；amplitudes、powers finite；outgoing-field match/passivity 全部适用项通过 |
| energy closure | `A_port_balance - A_volume = +8.177095667250001e-10`；raw `R+T+A_volume-1 = -8.177096777473025e-10`，其 absolute closure 为 `8.177096777473025e-10` |

独立 checker 仍严格使用原 A4 判据：`rho = eps_norm / max(rhs_norm, tiny)`，要求有限、非负且 `rho <= 1e-10`，并核对 raw/native residual 一致。254 次中 253 次通过，唯一失败为：

| 调用 | RHS norm | absolute residual | relative `rho` | 原 limit |
|---|---:|---:|---:|---:|
| PC sequence 2，第一次 p4 call | `0.800839353350057` | `2.3120761610371854e-10` | `2.8870661155266027e-10` | `1e-10` |

其余 253 次 `rho` 范围为 `9.620111350780948e-14` 至 `7.506926815015694e-11`。这是保留的真实数值负结果，不是 checker 接线 bug；没有放宽门槛、refinement 或重复回代。

MPC/矩阵身份也分列保存：`full_rows=667152`、`active_rows=199260`、`appended_ports=80`、`interior_rows=445500`、`slave_rows=22392`、`slave_master_entry_count=22392`；physical RHS packet SHA 为 `b85dde2599428906be4ffd2f2200438f3011e57358d20a541679b3ab50687824`，p6 native map SHA 为 `54647a99c97786af88364d6e3f8c6c1d3c7893bbf79afc2888a63cf47be6c06e`。

保存的生命周期 identity 中，before-factor、after-factor 和 before-release 的 CSR/mapping/values hash 一致：

- CSR：`857bc8bb5f04b28a55283fb960a2b695e1078983e55ff151687780de5dab8ee0`
- mapping：`bed2794532a40630632e06637cfda5a7bb52a06a7209824d5344085b6fa2cb1d`
- values：`cf081185f6950ebb2c704e0426e02bb0687ef7ae47faf34115d729c8eb832b34`

native numeric facts 中的 `matrix_identity_after_factor` 仍明确标为 `pending_post_factor_hash`；上面的 after/release 一致性来自已保存的生命周期 identity packet，不把 pending 字段冒充 fresh native hash。

## Watchdog phase、内存口径与 JIT

阶段由现有 `watchdog/resources.jsonl` 的 `worker_phase.phase` 聚合；阶段时差使用 `phase_started_clock.monotonic`，不使用跨 UTC 跳变的时钟。factor 阶段直到 solve phase 开始，包含 numeric 后的 H6/p6 setup，不能把整段约 674 秒称为纯 MUMPS numeric。

| watchdog phase | phase samples | duration / scope | RSS peak | PSS peak |
|---|---:|---|---:|---:|
| `preflight` | 17 | `4.312584284998593 s` | `427556864 B` | `394137600 B` |
| `setup` | 165 | `42.23196291399654 s` | `977985536 B` | `945806336 B` |
| `assembly` | 110 | `28.53227231799974 s` | `1802055680 B` | `1769876480 B` |
| `factor` | 2489 | `674.3087902290063 s`，含 numeric、H6/p6 setup 至 solve 起点 | `6969712640 B` | `6936216576 B` |
| `iteration/solve` | 17490 | `4810.633934284 s`，从 `36022.142617438` 开始，包含 setup PC | `7387607040 B` | `7355427840 B` |
| `postprocess/evaluation` | 60 | `16.41873642199789 s` | `7377305600 B` | `7343802368 B` |
| `cleanup` | 15 | `4.046380408999539 s`；duration basis 是 watchdog/resources.jsonl 最后一条 `parent_clock.monotonic=40853.102622218`，含退出清场 | `7377305600 B` | `7343802368 B` |

正式 numeric event 独立计时为 `222.35688313900027 s`；正式 solve 起点另为 `36064.707110545`，KSP 报告时间为 `4737.310983555995 s`，不与包含 setup PC 的 watchdog solve phase 或 full workflow 混称。全流程实测 monotonic 为 `5581.178597819002 s`；保守 policy workflow 为 `6079.400587860001 s`。

本场 11 个 qualified JIT modules 为 `11 hit / 0 miss`，compiler descendant samples 为 `0`，因此没有独立 compiler RSS 峰或可分离 compiler duration；当前缓存全命中。O10 historical 对照本身包含 p6 target cache miss/compile peak；旧 V22 正式场另为 `0 hit / 11 miss`，其编译 elapsed `101.78435976599758 s` 嵌套于旧 full workflow，不与总时长相加。两场冷/暖 JIT 口径分开，不把差异归因 CPU。

native 和 payload 口径严格分开：

| 对象 | 数值 | 口径 |
|---|---:|---|
| MUMPS `INFOG(19)` allocated | `4687 MB` | native decimal-MB读数 |
| allocated conservative upper | `4688000000 B` / `4688 MB` | `INFOG(19)+1 MB` 上界 |
| MUMPS `INFOG(22)` used | `4326 MB` | native decimal-MB读数 |
| used conservative upper | `4327000000 B` / `4327 MB` | `INFOG(22)+1 MB` 上界 |
| p6 cache payload | `450893192 B` | resident numerical payload，不是 RSS |
| full process-tree RSS peak | `7387607040 B` | watchdog simultaneous RSS measured |

V23 physical-memory policy 使用真实树 RSS、MemAvailable/cgroup 压力和 zero-swap/清场证据；本场只保留 `128 MiB` (`134217728 B`) 的 watchdog/write 证据余量，不再以旧 V22 的固定 6 GiB 库存、8 GiB 整树或 3.857 GB 续算上限阻断。详见 [user_authorization_v23_physical_memory.md](user_authorization_v23_physical_memory.md)。旧数字和旧负结果仍按原历史保留，不能追溯改判。

与 O10 同 scope 对照，B 为 `126` 步、KSP `4737.310983555995 s`，O10 为 `112` 步、KSP `1151.635034 s`；iterations 比 `1.125`（增加 `12.5%`），单步约由 `10.28246 s` 增至 `37.597706 s`，B/O10 RSS 比约 `2.60885`（B 峰值 `7387607040 B`，O10 `2831749120 B`）。O10 本身包含 p6 target cache miss/compile peak；这与旧 V22 冷 JIT 的 `11 miss` 分开，不把 payload 等同 RSS，也不把差异归因 CPU。

本场 native 读数为 `INFOG(1)=0`、`INFOG(9)=INFOG(29)=221594144`、`ICNTL(23)=4687 MB` 且 readback 为 `4687 MB`；`INFOG(19)=4687 MB` allocated 与 `INFOG(22)=4326 MB` used 仍分列。

## 费用、首场失败与 replay

| 成本项 | 时间 | 语义 |
|---|---:|---|
| 旧 V21 ledger | `1884.4679552510706 s` | 只读历史成本 |
| 旧 V22 ledger | `538.0163161130178 s` | 只读历史成本/RESOURCE_BLOCKED 负结果 |
| V21+V22 已知 ledger 累计 | `2422.4842713640884 s` | 仅已知 ledger，不是全部历史总时间 |
| V23 首场 implementation-bug 实测 | `379.43654483499995 s` | H6 affine geometry guard 失败，原记录保留 |
| V23 首场 policy/ledger | `414.7711851870877 s` | 保守结算，和实测分列 |
| V23 replay 实测 monotonic | `5581.178597819002 s` | process workflow measured |
| V23 replay policy workflow | `6079.400587860001 s` | conservative realtime policy |
| V23 replay settled ledger | `6079.411901537711 s` | ledger settled cost |
| 运行外工程修复/审核时间 | `unknown` | 未作完整独立测量，不写成 0 |

首场失败为 `NotImplementedError('only affine geometry is qualified')`，发生在 H6 setup；其 geometry root cause 是 cell 20 的绝对坐标消去误差。修复为两个 consumer 共用 16 行 `_affine_cell_jacobian`，平移坐标后保留原 `128 eps` guard、finite/positive determinant guard；几何定向测试 `16 passed`。资源/runtime/launcher/callback 定向验证共 `33 passed`，保存数据 checker 结果为 `58/59`；这些测试集合不相加。计算完成后的文档收口未新增测试、PDE 或旧资格重跑，Ruff/CI 也未宣称通过。

## 交付边界与下一研究对象

本轮状态为 `AWAITING_CHATGPT_REVIEW`、`NO_MERGE`、`NO_NEW_PDE_AFTER_THESE_RUNS`。现有证据支持：一次 fresh 和一次登记 bug replay 中 replay B 的完整求解、A6、场/物理输出、80 通道、资源清场、矩阵生命周期 identity 和真实资源成本。现有证据不支持：总体 checker PASS、在线 p4 A4 全部通过、同离散 reference match、C/notch 新结果、换 PC 或生产默认资格。

若后续另立研究对象，优先是同一 B/source 下对 PC2 首次 online A4 超限的数值缺陷做独立复现与修复审查；不得自动跑 C/notch、不得引入新 PC、不得放宽 `1e-10` 门槛。本交付 JSON 的 `metadata_commit_sha` 保持 `null`，由包含提交识别，不覆盖本次 formal source。

原始数据与紧凑证据入口见 `outcomes/records/dual_condensed_physical_memory_v23_{compact,decision,checker}.json`；raw run 保持在 ignored results 根，不将大型 field/matrix/factor/timeline 搬入 Git。文档记录不承诺额外自指补录提交。
