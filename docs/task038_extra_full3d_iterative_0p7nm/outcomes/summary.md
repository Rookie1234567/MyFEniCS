# Task038-extra Review V14 当前权威 summary

## 一句话结论

V13 C1 exact-input p6/h10 positive hierarchy 的 random、gradient、curl、checkerboard 四源均通过，selected hierarchy 保持为 `same_mesh_hcurl_pmg_v1_requalified`。V14 J5 v3 在同一 physical Maxwell workflow 的冷 staging、setup 和至少到 checkpoint-1000 的求解中完成了真实内存测量；raw timeline 随后继续约 `3896 s`，并在 checkpoint-1500 前由用户停止，实际停止迭代数 unavailable。分类为 `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED`，不是 fixed-cap 20000-step failure，也不是完整 workflow memory PASS。

positive source qualification 的通俗含义是：固定预条件器能在正定辅助算子上压低诊断误差；J5 physical 才包含波动、Floquet 和 streaming Fourier-DtN 的真实散射流程。前者不能代替后者。

## 当前阶段状态

| 阶段 | 当前权威状态 | 关键事实 |
|---|---|---|
| V11 S5 | frozen negative | 6→3 energy `0.04115402900674629 > 1e-9` |
| V12 | frozen historical negative | `selected_hierarchy=NONE`；identity、Route A/B/C2 negatives 保留 |
| V13 A0 | `CLOSED_BY_VECTOR_OR_STABLE_ADJOINT_GATE` | gradient pairwise-vs-compensated `2.7478465599487806e-12 > 1e-13`；MPI2/A1 未运行 |
| V13 C0 | `C0_CANONICAL_SOURCE_PASS_MPI1_MPI2` | canonical source/owner/phase Gate 通过 |
| V13 C1 | `C1_P6_POSITIVE_PASS_MPI1` | 四源 exact-input v4 通过；selected hierarchy=`same_mesh_hcurl_pmg_v1_requalified` |
| V13 P0 | `FAILED_RESOURCE_HARD_STOP` | cold setup peak `2,024,108,032 B`，超过 2,000,000,000 B `24,108,032 B` |
| V14 J4 | `J4_P0R_PASS` | one-cycle P0R qualification 已通过 |
| V14 J5 v3 | `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED` | 最后权威 checkpoint=1000；之后继续运行并在 checkpoint-1500 前停止；exact stop iteration unavailable |
| J6 | `not_run_by_J5_eligibility` | 未到 20000 步，long-tail eligibility 不成立 |
| J7/J8 | `locked/not_run` | 没有 solve-complete/recovery 前置证据 |
| official physics | `not_run` | E/H、near-field、R/T/A、`A_volume`、energy closure、12+12 arrays 均未生成 |
| ordinary default / master / full 0.7 nm PDE | unchanged / not_run | 本轮没有改动或启动 |

## V13 C1 positive qualification

| source | formal source SHA | iterations | final explicit true residual | peak / retained RSS | swap |
|---|---|---:|---:|---:|---:|
| random | `0da00e98c0423ade6cea38cabc3c8415ea32510e` | 200 | `5.550975220267439e-9` | 1,517,903,872 / 772,497,408 B | 0 |
| gradient | `82c56d92ac80ddf84071a6e1eff6d28e3513af7e` | 220 | `2.7889793119815017e-9` | 1,516,544,000 / 770,650,112 B | 0 |
| curl | `48866f2990a12113a28e556e6956104625b3da34` | 180 | `5.6105046279899595e-9` | 1,536,192,512 / 790,028,288 B | 0 |
| checkerboard | `80b0d8d36364007f4dda941d7770a307eee15dd4` | 200 | `7.760965317017376e-9` | 1,533,190,144 / 786,751,488 B | 0 |

四案绑定同一 exact input SHA `819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41`、physical model SHA `9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f`、mode manifest SHA `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`，profile 为 grazing=1°、theta=89°、phi=0°、13.5 nm、p6/h10、s。它们证明的是正定辅助 lane，不是 physical production qualification。

## Exact-input selected hierarchy size authority

下表复用同一 exact-input selected hierarchy 的 C1/setup authority；J5 没有 worker record，不把它冒充成 J5 fresh record。

| level | rows | global AIJ / NNZ |
|---|---:|---:|
| p6 high | 173,802 | global AIJ/NNZ `not materialized`（matrix-free） |
| p3 | 23,073 | `global_nnz=5,717,349` |
| p1 | 1,067 | `global_nnz=37,253` |
| p1 factor | 1,067 | `factor_matrix_nnz=131,203` |

## V13 P0 历史 hard stop

| 指标 | measured fact |
|---|---:|
| source SHA | `a05e93af6edb097c1f0ebf0f65e201698db27381` |
| stage | 仅 `paths_ready`；没有 bundle/setup/solve/recovery |
| elapsed / samples | 5167.201565908967 s / 20,518 |
| peak / hard line | 2,024,108,032 B / 2,000,000,000 B |
| overage | 24,108,032 B，约 1.2054%；严格 FAIL |
| swap / return | 0 B / -15；`process_tree_rss_limit` |

P0 没有 worker record、checkpoint、residual 或 official physics；该 negative 不是数值失败。原始 ignored root、tracked watchdog/path marker 和历史 SHA 保持不变。

## V14 J5 v3 measured stop

| 指标 | measured fact |
|---|---:|
| source SHA / profile | `ee5920b9fa977a39fea7bc09cfbe155303acdb2d` / p6/h10/13.5 nm/s/grazing1/phi0 |
| operator / solver | split matrix-free Maxwell volume + streaming Fourier-DtN；right GMRES restart20/max_it20000，replacement20 |
| raw samples | 334,915 |
| raw JSONL | 1,020,808,306 B；SHA `28c4044f3eebb72ca1991d1c71a67dd30637a7d550e798ffc7f536c28d969cf4` |
| raw first/last timestamp | `1788206276386617381` / `1788228581099334131`；window `22304.712716750 s` |
| solve start → last sample | `16477.100765097 s`；solve_started=`1788212103998569034` |
| full staged peak / swap | 1,450,262,528 B / 0 B |
| RSS/status / PSS readability | RSS/status fully readable；PSS 6 transient exit samples unavailable / solver compiler max 0 |
| marker boundary | 共 36 个 marker，最后 `035_solve_started` |
| checkpoint-500 | true residual `0.48387099430079733` |
| checkpoint-1000 | true residual `0.4837947981092168` |
| 500→1000 relative drop | `0.000157472120623114`，约 `0.01575%` |
| records / stderr | parent、worker、partial record absent；worker stderr 0 B |
| last authoritative checkpoint | 1000；manifest mtime 后 raw 仍约 3896 s；checkpoint-1500 absent；exact stop iteration unavailable |
| classification | `CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED` |

七个 cold precompile child 按固定顺序完成并观测到 11 个 `.so`；随后 solver 启动。用户停止后 parent、worker 和 `orted` 全部消失，JSONL 停止增长，checkpoint-500/1000 的 solution-only 文件完整保留。J5 v1/v2 execution negatives 也永久保留，均不被 v3 覆盖或重分类。

由于 worker/parent/partial record 均不存在，per-cycle residual history、actual stop iteration、matvec_count、pc_apply_count、ksp_destroy_count 和 driver elapsed_seconds 都 unavailable；不从 1000 步或实现公式猜测这些字段。RSS/status 完整可读不等于 PSS 完整可读：6 个 PSS 缺失只发生在 precompile 退出/zombie 瞬时样本。

## 物理 authority 与未运行项

J0 `AUTHORITY_ARRAYS_MISSING` 保持不变。当前 tracked direct authority 只有 scalar `R/T/A/A_volume`；没有 E/H、near-field 或同一 12 个 significant identities 的 12 power + 12 complex boundary-amplitude raw arrays。该下游 comparison blocker 未被伪装成通过，也不是 J5 本次停止原因。

| 项目 | 状态 |
|---|---|
| 2000/5000/10000/15000/20000 residual boundaries | `not_run_by_user_controlled_stop` |
| J6 bounded Floquet/near-cutoff correction | `not_run_by_J5_eligibility` |
| J7 release-before-recovery / official export | `locked/not_run` |
| J8 MPI2、h5、0.7 nm capacity | `locked/not_run` |
| official E/H/R/T/A/`A_volume`/channels | `not_run` |

## Selective merge boundary

| 分类 | 内容 | 决策 |
|---|---|---|
| reusable audit/canonical/resource candidates | stable-adjoint audit、canonical-vector helper、Task034 resource helper | 仍需 selective review；不等于 ordinary default |
| research-only | same-mesh pMG core、JIT/physical runners/checkers及 J4/J5 research workflow | C1 positive 保留；standalone physical claim 因 J5 controlled stop 关闭，不提升 production |
| do-not-promote | Route-A 6→3 candidate integration、旧 Route-B/C2/HX 失败路线 | 不作为 production numerical candidate；stable-adjoint audit helper 不属此类 |
| evidence/docs | V11/V12/V13/J5 negative compact、outcomes 和 responses | 可选择性合入作证据；提交负证据不等于合入失败 solver |

## 证据入口

| 内容 | 入口 |
|---|---|
| C0 canonical / C1 positive | [`same_mesh_canonical_source_v1.md`](same_mesh_canonical_source_v1.md) / [`p6_positive_v13.md`](p6_positive_v13.md) |
| V13 P0 | [`p6_physical_v13.md`](p6_physical_v13.md) |
| V14 J4/J5 memory | [`jit_staging_physical_memory_v14.md`](jit_staging_physical_memory_v14.md) |
| V14 J5 physical | [`p6_physical_v14.md`](p6_physical_v14.md) |
| J0 direct authority | [`direct_authority_packet_audit_v1.md`](direct_authority_packet_audit_v1.md) |
| J5 compact | [`j5_full_cold_staged_v3_controlled_stop_v14.json`](records/j5_full_cold_staged_v3_controlled_stop_v14.json) |
| V14 response | [`response_v14.md`](../response_v14.md) |
| historical responses | [`response_v11.md`](../response_v11.md) / [`response_v12.md`](../response_v12.md) |

完整 1.02 GB raw timeline、cache、markers 和 checkpoint 只留在 ignored artifact root，不加入 Git。V14 J9 在此停止，不创建新的 PC、J6、J7、J8 或 0.7 nm outcome。

## Review V15 F0–F4 最新结论

| 阶段 | 结果 | 证据边界 |
|---|---|---|
| F0 | 预测容量通过 | predicted central 1,555,934,144 B；不是 formal measured PASS |
| F1 small p3/h50 | F1_REAL_SMALL_ORACLE_PASS | MPI1/MPI2/checker 均 rc=0，canonical identity 通过 |
| F2 checkpoint-1000 | identity/algebra PASS | stored/recomputed residual relative 6.884466486395685e-16 |
| F3 fixed rank32 | FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE | captured 0.002179823642496248，rho 0.9989094935766222 |
| J5 V14 | CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED | 用户受控停止；不是 fixed-cap failure 或完整 memory PASS |

### F1 authority

F1 source SHA 为 fb1b4be71d230b77eff431a7e3dd77eb3a69ba69，root 为 f1_floquet_wave_small_oracle_v5/fb1b4be71d230b77eff431a7e3dd77eb3a69ba69。profile 为 p3/h50/13.5nm/s/grazing1/phi0；real operator oracle 只使用首个固定模式 mode_index=38、mode_key=[38,"top",0,0,"s"]。80-mode manifest SHA256 为 dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2；fixed selector SHA256 为 7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3。selector identity 覆盖 exact 32 indices，但不表示 32 个模式都分别运行了 real MPI oracle。

| F1 观测 | 数值 |
|---|---:|
| modal canonical MPI relative | 3.7455782853640207e-16 |
| PC canonical MPI relative | 8.520822093979077e-16 |
| modal repeat / linearity | 0 / 0 |
| PC repeat / input unchanged | 0 / 0 |
| PC linearity max | 3.614539850452157e-16 |
| P/P^H adjoint，MPI1 / MPI2 | 1.9465463728177503e-15 / 7.26427252913998e-15 |
| finite、slave-zero、owner-local、canonical keys | PASS |

独立 checker SHA256 为 506cbfbcbf6f4bb9e715f066506ed9011e1b6939e97992492ae2922f481ad9bf。record、四数组 NPZ、路径和 SHA 见 [F1 compact record](records/floquet_wave_small_oracle_v15.json)。

### V15 formal artifact v3：F2/F3 authority

V15 formal artifact v3 source SHA 为 c85ec1aab8548e02e8b47cfdcfb03b5c4df377f6，root 为 f2_f3_floquet_wave_cold_staged_v3/c85ec1aab8548e02e8b47cfdcfb03b5c4df377f6。parent 和 diagnostic natural exit=0，33 markers 到 parent_complete，7 个 child、11 modules、solver cache unchanged、全部进程消失。process samples=100656，window=6245.343577229 s，RSS peak=1,447,358,464 B，swap=0，warning=false，compiler peak=2；PSS peak=1,417,525,248 B，但 7 个 transient precompile 退出样本的 PSS 不可读，PSS 只作诊断。

| F2/F3 measured fact | 数值 |
|---|---:|
| checkpoint stored / recomputed residual | 0.4837947981092168 / 0.48379479810921644 |
| residual relative difference | 6.884466486395685e-16 <= 1e-11 |
| F2 identity、x/b unchanged、finite、slave-zero | PASS |
| F2 exact residual action | 1 |
| rank / condition ratio | 32 / 0.05087665596047715 |
| Q orthogonality / QR reconstruction | 1.4263744029917661e-13 / 2.4622854394555095e-16 |
| projection repeat | 2.7273607083155513e-16 |
| PC / exact action / modal RHS | 32 / 32 / 32 |
| captured energy / rho | 0.002179823642496248 / 0.9989094935766222 |
| ideal projected true residual | 0.4832672167742815 |

F3 algebra、QR、重复性、计数和资源通过；span 要求 captured 至少 0.90、rho 不大于 0.31622776601683794、ideal 不大于 0.153，故真实失败是 FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE，而非 resource 或 contract failure。完整 F3 记录见 [checkpoint checker output](records/floquet_wave_checkpoint1000_v15.json)。

F2 identity evidence 见 [F2 identity authority table](floquet_wave_residual_diagnostic_v15.md#f2-identity-authority)：normalized checkpoint input identity 为 754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f，operator identity 为 bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3，physical model 为 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f，mode manifest 为 dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2。template input file SHA 为 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41，不能与 normalized identity 混称。

### 历史边界与未运行项

V15 formal artifact v1/v2 pre-F2 execution failures 原样保留：v1 是 /proc transient-exit authority_unreadable race，v2 是 ModuleNotFoundError；它们发生在真实 checkpoint/数值测量前，按用户明确授权不计正式数值次数，但不改写 raw status/classification。V15 formal artifact v3 已进入真实 F2/F3，span 失败后不得重跑或改 rank/mode/参数。

J6 为 not_run_by_J5_eligibility；J7/J8 locked/not_run；fixed correction、KSP、corrected screen、recovery、official E/H/R/T/A、A_volume、12+12 channels、MPI2/h5/full 0.7 nm 均为 not_run_by_span_gate。V13 四类 same_mesh_hcurl_pmg_v1_requalified positive qualification 保留，但 standalone physical production claim 关闭。下一步仅提出 [wave-aware DD design](next_wave_aware_dd_after_v15.md)，不把它写成已授权实现或 J6 PASS。

V15 的完整阶段说明见 [residual diagnostic](floquet_wave_residual_diagnostic_v15.md)；J5 大 raw JSONL 1,020,808,306 B 只绑定 hash，不追踪原始文件。
