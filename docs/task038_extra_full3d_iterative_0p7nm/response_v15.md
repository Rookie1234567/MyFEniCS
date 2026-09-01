# Review V15 response

本响应按阶段区分了“通过”“真实负结果”“受控停止”和“未运行”。结论不是把波模诊断提升为新的生产求解器。

## 阶段结论

| 阶段 | 结果 | 可支持的结论 |
|---|---|---|
| F0 | 预测容量通过 | 可进入受控 small-oracle/F2/F3 设计；预测不是资源实测 |
| F1 | F1_REAL_SMALL_ORACLE_PASS | 真实 p3/h50、MPI1/MPI2 canonical identity 通过 |
| V14 J5 | CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED | 用户控制停止；不是 fixed-cap 20000-step failure |
| F2 | identity/algebra PASS | checkpoint-1000 的 exact A/b residual reproduction 通过 |
| F3 | FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE | rank、QR、重复性和资源通过；固定波模 span 失败 |
| J6/J7/J8 | not_run / locked | 没有 official physics 或 corrected solve |

## 用户明确的正式次数授权

用户明确授权：如果问题是在真实 checkpoint 或数值测量之前发生、且能够唯一定位为 code、path、marker、cache 或 provenance bug，则该次不计正式数值次数；流程是保留旧证据，做窄修和 focused test，经审阅并提交后，用新的 source SHA 和新的 artifact root 重试。只有 identity、numerical/span、2 GB、swap 或 nonfinite 等真实 Gate 才停止正式资格化。

因此，F2/F3 v1 和 v2 的 pre-measurement 失败按该授权保留，旧 root 不覆盖、不重分类。v3 已经完成真实 F2 和 F3，span Gate 是实际数值失败；不得再次运行，也不得改 rank、mode 或参数来规避。

## F1 authority

| 项目 | frozen fact |
|---|---|
| source SHA | fb1b4be71d230b77eff431a7e3dd77eb3a69ba69 |
| artifact root | benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/f1_floquet_wave_small_oracle_v5/fb1b4be71d230b77eff431a7e3dd77eb3a69ba69 |
| classification | F1_REAL_SMALL_ORACLE_PASS |
| checker SHA256 | 506cbfbcbf6f4bb9e715f066506ed9011e1b6939e97992492ae2922f481ad9bf |
| MPI1 record / NPZ SHA256 | a84b723606a441a151c9c9a5ef86129679ccbe95a0556b98d4c2c5f76a3ca401 / 55f9efaccb37a8f87cb656b73dd23487879f0b272baa97d52812f3184e544b5f |
| MPI2 record / NPZ SHA256 | 45164cdfe69a758bab25b833e1fcf2bdae488f56f5d1a24692afd54784ca7e36 / 66bf1e66334a3b4661cfebd03b50ae8f82233ad7bc649a4fd91aec5324489f89 |

| F1 Gate | measured |
|---|---:|
| modal canonical MPI relative | 3.7455782853640207e-16，限值 1e-12 |
| PC canonical MPI relative | 8.520822093979077e-16，限值 1e-10 |
| modal repeat / linearity | 0 / 0 |
| PC repeat / input unchanged | 0 / 0 |
| PC linearity max | 3.614539850452157e-16 |
| P/P^H adjoint，MPI1 / MPI2 | 1.9465463728177503e-15 / 7.26427252913998e-15，限值 1e-11 |
| finite、slave-zero、owner-local、canonical keys | PASS |

80-mode manifest SHA256 为 dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2；固定 32-index selector SHA256 为 7a6dea2534b200c6572b0200acd77087c71ccb0e52a0d1a16dae75e108cee2c3。profile 为 p3/h50/13.5nm/s/grazing1/phi0；real operator oracle 只使用首个固定模式 mode_index=38、mode_key=[38,"top",0,0,"s"]，selector identity 虽覆盖 exact 32 indices，但不表示 32 个模式都分别运行了 real MPI oracle。F1 compact 见 [small-oracle record](outcomes/records/floquet_wave_small_oracle_v15.json)。

## V15 formal artifact v1/v2 pre-F2 execution failures

| root | 实际事实 | 不应作出的结论 |
|---|---|---|
| f2_f3_floquet_wave_cold_staged_v1/87b71b346580f57926b6dbd87e6ee1a408380bea | /proc transient-exit race 触发 authority_unreadable；未进入 F2/F3 | 不是 numerical、resource 或 span failure |
| f2_f3_floquet_wave_cold_staged_v2/7adaea8fa8bb17488f094a55b3f777b88e2b7f99 | source import ModuleNotFoundError；未进入 F2/F3；RSS 1,580,867,584 B、swap 0 | 不是 checkpoint identity 或 numerical failure |

v1 parent/process/marker SHA256 分别为 7833cf725d15626c72170a3591435684965aaa0f35f7d0d03b44c2986c534ab6、b8c1628400276df7a3105af3afe8c65dac7eed5d3c85d866541df17a8ad95c6b、8129248d43036dfa3462e37e338eff20ec2ad8d2a0d3651e68bfad5e7f8c9305。v2 parent/process/marker/stderr SHA256 分别为 af587557dd7e5c070d955b44fd8a78c56261390a42974b0245ab3432ccf53f88、ecce7ec5471d80056cff926c2ca491cebfa76f6e64ac854e6319282df669c26c、483d10f4fd23a9b726e6ccb68bbcb52e561a1234dfe3a4689488e5ccb387f806、c781c19f5fcf8e511801dee5133f2519c39b41c238cbfe39526b91fb1f416690。

## V15 formal artifact v3：F2/F3

V15 formal artifact v3 source SHA 为 c85ec1aab8548e02e8b47cfdcfb03b5c4df377f6，root 为 benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/f2_f3_floquet_wave_cold_staged_v3/c85ec1aab8548e02e8b47cfdcfb03b5c4df377f6。parent、diagnostic 均自然退出 0，33 markers 到 parent_complete，七组 child 正常退出，11 modules，solver cache unchanged 且无 recompile，全部进程消失。

| 资源/生命周期 | measured |
|---|---:|
| process samples / window | 100656 / 6245.343577229 s |
| complete process-tree RSS peak | 1,447,358,464 B |
| swap / warning | 0 B / false |
| compiler descendants peak | 2 |
| max readable PSS | 1,417,525,248 B |

PSS 有 7 个 transient precompile 退出样本不可读；RSS/status 样本完整可读。PSS 只是诊断指标，不能替代 RSS Gate。

F2 使用 checkpoint iteration 1000。stored true residual 为 0.4837947981092168，重算为 0.48379479810921644，relative difference 为 6.884466486395685e-16，限值 1e-11。checkpoint identity、x/b unchanged、finite、slave-zero 和一次 exact residual action 均通过；这只表示 identity/algebra residual reproduction PASS。

### F2 identity authority

| identity | exact SHA256 |
|---|---|
| checkpoint normalized input identity | 754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f |
| operator identity | bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3 |
| physical model identity | 9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f |
| mode manifest identity | dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2 |
| input file SHA256（独立于 normalized identity） | 819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41 |

checkpoint normalized input identity 是 reader 的 frozen authority；input file SHA 是 template 文件本身，不能用文件 SHA 代替 normalized identity。

F3 的 rank=32，condition ratio=0.05087665596047715，Q orthogonality=1.4263744029917661e-13，QR reconstruction=2.4622854394555095e-16，projection repeat=2.7273607083155513e-16；PC/exact action/modal RHS count=32/32/32。列均 finite、input unchanged、slave-zero，资源也通过。

独立 checker 重算 captured energy=0.002179823642496248，要求至少 0.90；rho=0.9989094935766222，要求不大于 0.31622776601683794；ideal projected true residual=0.4832672167742815，要求不大于 0.153。固定 32 个波模只解释约 0.218% 的残差能量，投影几乎没有改善。因此分类固定为 FLOQUET_WAVE_CORRECTION_CLOSED_BY_SPAN_GATE，checker 输出见 [checkpoint checker record](outcomes/records/floquet_wave_checkpoint1000_v15.json)，其 SHA256 为 e231b57dfcfff8fe44352ed5c0f5a7c0b75564b74aaf54b50655f71eec7f5def。

## J5 与未运行项

### V14 J5 v3 受控停止事实

| 项目 | measured fact |
|---|---|
| source / root | ee5920b9fa977a39fea7bc09cfbe155303acdb2d；j5_full_cold_staged_v3/ee5920b9fa977a39fea7bc09cfbe155303acdb2d |
| checkpoint-500 / checkpoint-1000 true residual | 0.48387099430079733 / 0.4837947981092168 |
| 500 到 1000 relative drop | 0.000157472120623114，约 0.01575% |
| process-tree peak / swap | 1,450,262,528 B / 0 |
| raw samples / JSONL bytes | 334,915 / 1,020,808,306 B |
| raw JSONL SHA256 | 28c4044f3eebb72ca1991d1c71a67dd30637a7d550e798ffc7f536c28d969cf4 |
| first / last timestamp_ns | 1788206276386617381 / 1788228581099334131 |
| solve_started 到最后样本 | 16,477.100765097 s；solve_started=1788212103998569034 |
| marker boundary | 035_solve_started；没有 solve_complete、recovery 或 official marker |

最后一个有完整权威文件的 checkpoint 是 1000；其 manifest mtime 后 raw 仍继续约 3896 s，checkpoint-1500 不存在，因此 exact stop iteration unavailable。worker、parent、partial record 均 absent，worker stderr 为 0 B；per-cycle residual history、actual stop iteration、matvec/PC/KSP-destroy counts 和 driver elapsed_seconds 均 unavailable，不能从迭代数或实现公式推算。checkpoint-500/1000 是完整 solution-only 文件。process-tree RSS/status 的上述资源实测只覆盖用户控制停止点，不是完整 workflow memory PASS。

J5 的分类固定为 CONTROLLED_STOP_USER_NUMERICAL_STAGNATION / NOT_QUALIFIED，不是 fixed-cap 20000-step failure，也不是完整 workflow memory PASS。

F3 失败后，fixed rank32 correction、KSP、corrected screen、recovery、official E/H/R/T/A、A_volume、12+12 channels、MPI2/h5/full 0.7 nm 均为 not_run_by_span_gate。J6 为 not_run_by_J5_eligibility；J7/J8 locked/not_run。J0 AUTHORITY_ARRAYS_MISSING 继续存在；不能用缺失的 official arrays 虚构通过。

V13 四类 same_mesh_hcurl_pmg_v1_requalified positive qualification 保留，但 standalone physical Maxwell production claim 关闭/未资格化。

## 下一步：未授权的 wave-aware DD 预审

唯一未授权候选是独立的 wave-aware domain decomposition 预审，不是 V15 rank32 global projection 的重跑，也不产生 bounded correction numerical implementation。它由 local matrix-free Maxwell subdomain inverse、显式包含 gradient 与 propagating/near-cutoff physics 的 interface coarse space，以及 fixed-memory owner-distributed coarse operator/solve 组成。

不得重跑 V15 rank32 global projection 或 bounded correction，不得把普通 GenEO、BDDC 或 HX 换名重开。保留已经通过的低内存 same-mesh pMG，只把它作为局部基础。下一次 review 前仅闭合 action/interface 数学 identity、物理 basis 的 rank scaling 和小于 2 GB 的 simultaneous capacity 预审；本阶段没有 numerical implementation。V14 J6 仍 not_run，不能把该提案写成 J6 PASS。

## 证据边界

完整 J5 raw JSONL 为 1,020,808,306 B，不追踪该 1.02 GB 文件；文档只绑定 compact/hash。V15 formal artifact v1/v2 pre-F2 execution failures、V14 J5 controlled stop 和 V15 formal artifact v3 span checker 输出不删除、不覆盖、不重分类。V15 compact 见 [F1 record](outcomes/records/floquet_wave_small_oracle_v15.json)，wave-aware DD 设计见 [next candidate](outcomes/next_wave_aware_dd_after_v15.md)。
